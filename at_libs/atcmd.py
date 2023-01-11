import re
import time
from abc import ABC, abstractmethod
from typing import Union, Optional,List

import serial
from serial import Serial

RE_RESPONSE = re.compile(br"^AT.*?(?:(?:^OK)|(?:^ERROR)|(?:^\+CMS ERROR: .+?)|(?:^\+CME ERROR: .+?))\r\n", re.MULTILINE | re.DOTALL)
GUARD_DELAY_S = 0.2


def param_str_repres(param: Union[str, int]) -> str:
    if isinstance(param, str):
        return f'"{param}"'
    elif isinstance(param, int):
        return str(param)
    else:
        raise TypeError

#def params_str(params: Optional[Union[str, int, list[str, int]]]) -> str:
def params_str(params) -> str:
    if isinstance(params, list):
        return ','.join([param_str_repres(param) for param in params])
    elif params is not None:
        return param_str_repres(params)
    else:
        ""


def param_bytes_repres(param: Union[str, int]) -> bytes:
    as_str = param_str_repres(param)
    return as_str.encode("ASCII")


#def params_bytes(params: Optional[Union[str, int, list[str, int]]]) -> bytes:
def params_bytes(params) -> bytes:
    if isinstance(params, list):
        return b','.join([param_bytes_repres(param) for param in params])
    elif params is not None:
        return param_bytes_repres(params)
    else:
        b''


class AtCmd(ABC):
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def name_bytes(self) -> bytes:
        return self.name.encode("ASCII")


class AtCmdBasic(AtCmd):
    """
    Name is full name (ex: ATE, AT, ATI)
    """

    def __init__(self, name: str):
        name = name.upper()
        assert name.startswith("AT") and name.isalnum()
        super().__init__(name)
    #def write_cmd(self, params: Optional[Union[str, int, list[Union[str, int]]]] = None) -> bytes:
    def write_cmd(self, params= None) -> bytes:
        cmd = self.name_bytes
        if params is None:
            return cmd
        else:
            params = params_bytes(params)
            return cmd + params

    def __str__(self) -> str:
        return self.name


class AtCmdExt(AtCmd):
    """
    Name is without the AT+ part (ex: CPINATI)
    """

    def __init__(self, name: str):
        name = name.upper()
        assert (not name.startswith("AT")) and name.isalnum()
        super().__init__(name)

    def test_cmd(self) -> bytes:
        return self.encoded_bytes() + b'=?'

    def query_cmd(self) -> bytes:
        return self.encoded_bytes() + b'?'
    #def write_cmd(self, params: Optional[Union[str, int, list[Union[str, int]]]]) -> bytes:
    def write_cmd(self, params) -> bytes:
        cmd = self.encoded_bytes()
        params = params_bytes(params)
        return cmd + b'=' + params

    def execution_cmd(self) -> bytes:
        return self.encoded_bytes()

    def __str__(self) -> str:
        return f'AT+{self.name}'

    def encoded_bytes(self) -> bytes:
        return b'AT+' + self.name_bytes


AT = AtCmdBasic("AT")

ATE = AtCmdBasic("ATE")

CPIN = AtCmdExt("CPIN")



class SerialModem:
    def __init__(self, port: str, pin: str):
        self._ser = Serial(port=port,
                           baudrate=115200,
                           bytesize=serial.EIGHTBITS,
                           parity=serial.PARITY_NONE,
                           stopbits=serial.STOPBITS_ONE,
                           timeout=20,
                           xonxoff=False,
                           rtscts=False,
                           write_timeout=None,
                           dsrdtr=False,
                           inter_byte_timeout=None,
                           exclusive=True, )
        if not self._ser.is_open:
            self._ser.open()
            assert self._ser.is_open

        print("Opened serial communication")

        time.sleep(GUARD_DELAY_S)

        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

        self._last_command_sent_time = time.time()
        response = self.send_command_get_answer(ATE.write_cmd(1))[0]
        assert response.endswith("OK")

        print("Enabled ATE, querying PIN...")

        response = self.send_command_get_answer(CPIN.query_cmd())[0]
        assert response.endswith("OK")
        if "+CPIN: SIM PIN" in response:
            print("Inputing PIN...")
            response = self.send_command_get_answer(CPIN.write_cmd(pin))[0]
            assert response.endswith("OK")
            print("Waiting for init after PIN...")
            time.sleep(3)
            urc = self.read_lines_until_empty()
            response = urc

        if "+CPIN: READY" not in response:
            raise NotImplementedError("Pin failure handling not implemented")

        print(f"Modem at {port} initialized!")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ser.close()

    def _read_until_empty(self) -> str:
        data = bytearray()
        assert self._ser.is_open
        while self._ser.in_waiting > 0:
            b = self._ser.read(self._ser.in_waiting)
            data.extend(b)

        return data.decode("ASCII")

    def read_lines_until_empty(self) -> str:
        """
        Should be ok as every terminal output should end with a newline
        """
        data = bytearray()
        assert self._ser.is_open
        while self._ser.in_waiting > 0:
            b = self._ser.readline()
            data.extend(b)

        return data.decode("ASCII", errors="ignore")

    def send_command(self, cmd: bytes):
        """
        :param cmd:
        :return: returns true if some unprocessed input has been found
        """
        assert self._ser.is_open
        time_since_last = time.time() - self._last_command_sent_time
        remaining_wait = GUARD_DELAY_S - time_since_last

        if remaining_wait > 0.0:
            time.sleep(remaining_wait)

        self._ser.write(cmd + b'\r\n')
        self._ser.flush()
        time.sleep(GUARD_DELAY_S)

    def send_data(self, data: bytes):
        """
        Should only be used after a command that requires more data, such as the content of an SMS
        """
        assert self._ser.is_open
        time_since_last = time.time() - self._last_command_sent_time
        remaining_wait = GUARD_DELAY_S - time_since_last

        if remaining_wait > 0.0:
            time.sleep(remaining_wait)

        self._ser.write(data)
        self._ser.flush()
        time.sleep(GUARD_DELAY_S)

    def read_response(self) -> (str, str):
        """
        As every command must end with specific messages, we can read until them
        :return: returns the response, as well as any preceding input (mainly urc)
        """
        response = b''
        while (find := RE_RESPONSE.search(response)) is None:
            response += self._ser.readline()

        urc_data = response[:find.start()].decode("ASCII").strip()

        response = find.group().decode("ASCII", errors="ignore").strip()

        return response, urc_data

    def send_command_get_answer(self, cmd: bytes) -> (str, str):
        """
        :return: returns the response, as well as any preceding input
        """
        self.send_command(cmd)
        return self.read_response()
