import machine
import network
import micropython
from umqtt.simple import MQTTClient
from machine import Pin
from hcsr04 import HCSR04
import time

ABIERTO = 0
CERRADO = 1
ABRIENDO = 2
CERRANDO = 3
DETENIDO = 4
FALLA_MECANICA = 5

ABRIR = 0
CERRAR = 1

FACTOR_DIFERENCIA = 4
DIST_DETECCION_PORTON = 5
DIST_DETECCION_OBSTRUCCION = 20

sensorA = HCSR04(trigger_pin=1, echo_pin=0)
sensorC = HCSR04(trigger_pin=3, echo_pin=2)
releMotorA = Pin(4, Pin.OUT)
releMotorC = Pin(5, Pin.OUT)

comando = None
estado = ABIERTO

distAntSensA = 0
distAntSensC = 0
difAntSensA = 0
difAntSensC = 0

ultimoEstadoPublicado = None
ultimoColorPublicado = None

def funcionCallback(topic, msg):
    global comando

    data = msg.decode("utf-8")
    topicData = topic.decode("utf-8")

    print("Mensaje recibido del topico: " + topicData + " mensaje: " + data)

    if (topicData == topicoPorton and "Abrir" in data):
        comando = ABRIR
    else:
        comando = CERRAR

def estadoACadena (estado):

    if estado == ABIERTO:
        ret = "Abierto"
    elif estado == CERRADO:
        ret = "Cerrado"
    elif estado == ABRIENDO:
        ret = "Abriendo"
    elif estado == CERRANDO:
        ret = "Cerrando"
    elif estado == DETENIDO:
        ret = "Detenido"
    elif estado == FALLA_MECANICA:
        ret = "Falla mecanica"
    else:
        ret = "ERROR"
    
    return ret

def calcularEstado (distSensA, distSensC, difAct, difAnt):
    global estado

    print("Distancias")
    print(distSensA)
    print(distSensC)
    print(difAct)
    print(difAnt)

    print("Estado")

    # Logica de obstrucciones
    if (estado == ABRIENDO or estado == CERRANDO):

        # En la primer lectura, difAnt = 0 pero difAct > 0, por lo que activará el estado detenido.
        # Para evitar esto, no se realiza la verificación en la primer lectura. Esto se puede hacer
        # sin vulnerar el mecanismo de seguridad ya que antes de iniciar el movimiento verifica
        # si hay obstrucciones.
        if (difAnt > 0 and difAct > difAnt * FACTOR_DIFERENCIA):
            releMotorA.value(0)
            releMotorC.value(0)
            estado = DETENIDO
            print(estado)

        if (difAct == difAnt and estado != DETENIDO):
            releMotorA.value(0)
            releMotorC.value(0)
            estado = FALLA_MECANICA
            print(estado)           

    if (estado == DETENIDO):
        time.sleep_ms(1000)

        if (comando == CERRAR and distSensC > DIST_DETECCION_OBSTRUCCION):
            releMotorC.value(1)
            estado = CERRANDO
            print(estado)

        if (comando == ABRIR and distSensA > DIST_DETECCION_OBSTRUCCION):
            releMotorA.value(1)
            estado = ABRIENDO
            print(estado)

    # Funcionalidad base de apertura y cierre
    if (estado == ABIERTO and comando == CERRAR and distSensA < DIST_DETECCION_PORTON):
        
        if (distSensC > DIST_DETECCION_OBSTRUCCION):
            estado = CERRANDO
            releMotorC.value(1)
        else:
            releMotorC.value(0)
            estado = DETENIDO

        print(estado)

    if (estado == CERRADO and comando == ABRIR and distSensC < DIST_DETECCION_PORTON):

        if (distSensA > DIST_DETECCION_OBSTRUCCION):
            estado = ABRIENDO
            releMotorA.value(1)
        else:
            releMotorA.value(0)
            estado = DETENIDO
            
        print(estado)

    # Fin del recorrido
    if (estado == ABRIENDO and distSensA < DIST_DETECCION_PORTON):
        releMotorA.value(0)
        estado = ABIERTO
        print(estado)

    if (estado == CERRANDO and distSensC < DIST_DETECCION_PORTON):
        releMotorC.value(0)
        estado = CERRADO
        print(estado)

def asignarColorDeEstado (estado):
    color = ""

    if estado == DETENIDO:
        color = "#FFFF00"
    elif estado == ABIERTO:
        color = "#00FF00"
    elif estado == CERRADO:
        color = "#FF0000"
    elif estado == ABRIENDO:
        color = "#90EE90"
    elif estado == CERRANDO:
        color = "#FF7F7F"
    else:
        color = "error"

    return color

# Logica de conexion a internet

ssid = "Wokwi-GUEST"
wifiPassword = ''

staIf = network.WLAN(network.STA_IF)
staIf.active(True)

staIf.connect(ssid, wifiPassword)
print("Conectando")

while not staIf.isconnected():
    print(".", end="")
    time.sleep(0.1)

print("Conectado a WiFi")

print(staIf.ifconfig())

mqttServer = "io.adafruit.com"
port = 1883
user = "Due_Ad"
password = ""

clientID = "MiPortonIOT"
topicoPorton = "Due_Ad/feeds/AbrirCerrarPorton"
topicoEstado = "Due_Ad/feeds/EstadoDelPorton"
topicoLuz = "Due_Ad/feeds/ColorLed"

try:
    conexionMQTT = MQTTClient(clientID, mqttServer, user = user, password = password, port = int(port))
    conexionMQTT.set_callback(funcionCallback)
    conexionMQTT.connect()
    conexionMQTT.subscribe(topicoPorton)
    print("Conectado con broker MQTT")
except OSError as e:
    print("Error de conexion: ", e)
    time.sleep(5)
    machine.reset()


while True:
    time.sleep_ms(1000)

    try:
        conexionMQTT.check_msg()

        distSensA = round(sensorA.distance_cm())
        distSensC = round(sensorC.distance_cm())

        difActSensA = abs(distAntSensA - distSensA) 
        difActSensC = abs(distAntSensC - distSensC) 

        if (comando == ABRIR):
            calcularEstado(distSensA, distSensC, difActSensA, difAntSensA)
        else:
            calcularEstado(distSensA, distSensC, difActSensC, difAntSensC)

        #print(comando)
        #print(estadoACadena(estado))

        estadoActual = estadoACadena(estado)

        # Pulicar estado al dashboard
        if estadoActual != ultimoEstadoPublicado:
            conexionMQTT.publish(topicoEstado, estadoActual)
            ultimoEstadoPublicado = estadoActual

        color = asignarColorDeEstado(estado)

        # Publicar el color al dashboard
        if color != ultimoColorPublicado:
            conexionMQTT.publish(topicoLuz, color)
            ultimoColorPublicado = color

        if estadoActual == "Falla mecanica":
            print("Falla mecanica del porton")
            time.sleep(5)
            machine.reset()            

        distAntSensA = distSensA
        distAntSensC = distSensC
        difAntSensA = difActSensA
        difAntSensC = difActSensC

    except OSError as e:
        print("Error de conexion: ", e)
        time.sleep(5)
        machine.reset()
