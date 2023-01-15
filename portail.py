import time
import serial
from at_libs.atcmd import *

DEVICE_PORT = "/dev/ttyUSB2"
DEVICE_PIN = "0000"

#utile
eof=bytes.fromhex('1A')
numOnnig="0695468015"

#commande at+
CMGS = AtCmdExt("CMGS")#envoie un SMS
CMGF= AtCmdExt("CMGF")#met le format des SMS
AUTOANSWER=AtCmdExt("AUTOANSWER")#repond auto
CLIP=AtCmdExt("CLIP")#identification de l'appelant
CNMP=AtCmdExt("CNMP")#change le mode de com
CGSOCKCONT=AtCmdExt("CGSOCKCONT")#defini le context du socket
CSOCKAUTH=AtCmdExt("CSOCKAUTH")#fixe l'authentification du socket
CHTTPACT=AtCmdExt("CHTTPACT")#fait requete HTTP
CHUP=AtCmdExt("CHUP")#raccroche
ATA=AtCmdBasic("ATA")#répond
FSLS=AtCmdExt("FSLS")#fait un ls
FSCD=AtCmdExt("FSCD")#change le repertoire courant
CCMXPLAY=AtCmdExt("CCMXPLAY")#joue music
pathRessource="D:"

def printUntilString(string):
    while True:#attente infini
        print("on attend "+string)
        rep = getLineInString()
        print(rep)
        if (string in rep):
            print("trouver")
            break
        time.sleep(0.1)


#met le bon mode PDU pour envoyer des SMS
def initSMS():
    modem.send_command(CMGF.write_cmd(1))
    #print(getLineInString())
    #modem.read_response()
    printUntilString("CMGF")

def lsDirectory():
    modem.send_command(FSCD.encoded_bytes())
    print(getLineInString())

def initRessource(path):
    modem.send_command(FSCD.encoded_bytes())
    #print(getLineInString())
    printUntilString("FSCD")


#s'authentifie pour pouvoir utiliser GPRS
def initAuthTCP():
    modem.send_command(CSOCKAUTH.write_cmd([1,0]))
    #print(getLineInString())
    #modem.read_response()
    printUntilString("CSOCKAUTH")

#passe en mode UMTS only
def modeUMTS():
    modem.send_command(CNMP.write_cmd(14))
    #print(getLineInString())
    printUntilString("CNMP")
#établi une connexion avec l'APN : gateway de l'internet
def initAPN():
    modem.send_command(CGSOCKCONT.write_cmd([1,"IP","mmsbouygtel.com"]))
    #print(getLineInString())
    printUntilString("CGSOCKCONT")


urlOfRandomNumber="calculator.net"
getRequest="/random-number-generator.html?slower=0&supper=1&ctype=1&s=3860&submit1=Generate"
startOfAnswer="<h2 class=\"h2result\">Result</h2><p class=\"verybigtext\" style=\"word-wrap: break-word;padding: 10px 0px;\">"
def randomNumberOfHTTPGet():
    print("on envoie la request")
    modem.send_command(CHTTPACT.write_cmd([urlOfRandomNumber, 80]))
    print("command sent")
    printUntilString("CHTTPACT: REQUEST")
    modem.send_data(b'GET /random-number-generator.html?slower=0&supper=1&ctype=1&s=3860&submit1=Generate \r\n\r\n')
    modem.send_data(eof)
    print("on a envoyer la requete")
    reponse = [getLineInString()]
    while ("CHTTPACT: 0" not in reponse[-1]):
        #print(reponse[-1])
        if("h2result" in reponse[-1]):
            print("trouvée "+reponse[-1])
            resu=reponse[-1].split('break-word;padding: 10px 0px;">')[1][:1]
            print("reponse "+resu)
            modem._ser.flush()
            return resu
        reponse.append(getLineInString())
    if (startOfAnswer in reponse[-1]):
        return reponse[-1]
    else:
        return reponse


#requete HTTP de l'url passé en param
def getHTTP(url):
    modem.send_command(CHTTPACT.write_cmd([url,80]))
    printUntilString("CHTTPACT: REQUEST")
    modem.send_data(b'GET / \r\n\r\n')
    modem.send_data(eof)
    print("on a envoyer la requete")
    reponse=[getLineInString()]
    while ("CHTTPACT: 0" not in reponse[-1]):
        print(reponse[-1])
        reponse.append(getLineInString())
    return reponse


def sendSMStoNum(num,message):
    initSMS()
    modem.send_command(CMGS.write_cmd(num))
    time.sleep(1)
    modem.send_data(bytes(message,"utf-8"))
    modem.send_data(eof)
    print("sent")
    print(getLineInString())
    print("fini")

def playSoundAtPath(path,name):#le path est le dossier parent du name
    initRessource(path)
    modem.send_command(CCMXPLAY.write_cmd([name,1]))
    while True:
        print(getLineInString())

def getGoogle():
    modeUMTS()
    initAPN()
    initAuthTCP()
    resu=getHTTP("google.fr")
    #print(resu)

#montre qui appelle après ring
def enableCallerIDVisible():
    modem.send_command(CLIP.write_cmd(1))
    #print(getLineInString())
    printUntilString("CLIP")


#tout est dans le nom
def answer():
    modem.send_command(ATA.write_cmd())
    printUntilString("ATA")


def waitForCallAndGetNumber():
    print("mise en attente")
    printUntilString("RING")
    str(modem._ser.readline())
    rep = str(modem._ser.readline())[2:-1]
    #répond et raccroche après avoir eu l'info du numéro
    answer()
    time.sleep(1)
    hangup()
    print("on a raccroché")
    return rep[len("+CLIP: \""):len("+CLIP: \"") + 12]

def getLineInString():
    rep=modem._ser.readline().decode().strip("\\n")#.strip("\\r")[2:-1]
    return rep


def enableAutoAnswer():
    modem.send_command(AUTOANSWER.write_cmd(1))
    printUntilString("AUTOANSWER")

def hangup():
    modem.send_command(CHUP.encoded_bytes())
    printUntilString("CHUP")



if __name__ == "__main__":
    with SerialModem(DEVICE_PORT, DEVICE_PIN) as modem:
        #test d'envoie reponse de AT
        (response, urc) = modem.send_command_get_answer(AT.write_cmd())
        assert response.endswith("OK")
        print(f"URC received since last:\n{urc}")
        print(f"Response:\n{response}")
        time.sleep(1)
        #playSoundAtPath(pathRessource,"oof.amr") #marche pas :c
        #enableAutoAnswer()
        modeUMTS()
        initAPN()
        initAuthTCP()
        enableCallerIDVisible()
        while(True):
            numberCalling=waitForCallAndGetNumber()
            print(numberCalling+" is calling !")
            answerRandom=randomNumberOfHTTPGet()
            answerSMS=""
            if (answerRandom == None):
                answerSMS="site down"
            if(answerRandom=="1"):
                answerSMS="le portail s'ouvre\nbienvenue"
            elif(answerRandom=="0"):
                answerSMS="access denied"
            if(answerSMS!=""):
                sendSMStoNum(numberCalling,answerSMS)
            print("reponse a envoyer "+answerSMS)