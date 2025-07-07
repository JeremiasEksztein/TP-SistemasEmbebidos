import machine
import network
import micropython
from umqtt.simple import MQTTClient
from machine import Pin
from hcsr04 import HCSR04
import time

# Definiciones de constantes
ABIERTO = 0
CERRADO = 1
ABRIENDO = 2
CERRANDO = 3
OBSTRUIDO = 4
FALLA_MECANICA = 5

ABRIR = 0
CERRAR = 1

FACTOR_DIFERENCIA = 4
DIST_DETECCION_PORTON = 5
DIST_DETECCION_OBSTRUCCION = 20

# Sensores y actuadores
sensorA = HCSR04(trigger_pin=1, echo_pin=0)
sensorC = HCSR04(trigger_pin=3, echo_pin=2)
releMotorA = Pin(4, Pin.OUT)
releMotorC = Pin(5, Pin.OUT)

# Variables
comando = None
estado = None

tEstatico = 0

distAntSensA = 0
distAntSensC = 0
difAntSensA = 0
difAntSensC = 0

ultimoEstadoPublicado = None
ultimoColorPublicado = None

# Funciones
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
    elif estado == OBSTRUIDO:
        ret = "Obstruido"
    elif estado == FALLA_MECANICA:
        ret = "Falla mecánica"
    else:
        ret = "ERROR"
    
    return ret

def manejarFallaMecanica (distSensA, distSensC, distAntSensA, distAntSensC):

    global estado
    global tEstatico

    if (estado == ABRIENDO or estado == CERRANDO):

        # Cada segundo que el porton queda en la misma posición respecto a los sensores
        # se suma uno al contador tEstatico
        if (distSensA == distAntSensA and distSensC == distAntSensC):
            tEstatico = tEstatico +1
        else:
            tEstatico = 0

        print("Tiempo estatico:", tEstatico, "s")

        # Al llegar a 10 segundos se estancamiento del portón, se asume una falla mecánica
        if (tEstatico == 10):
            releMotorA.value(0)
            releMotorC.value(0)
            estado = FALLA_MECANICA
            print(estado)  

def manejarObstruccion (distSensA, distSensC, distAntSensA, distAntSensC):

    global estado, difActSensA, difAntSensA, difActSensC, difAntSensC

    difActSensA = abs(distAntSensA - distSensA)
    difActSensC = abs(distAntSensC - distSensC)

    # Detección de obstrucciones
    if (estado == ABRIENDO or estado == CERRANDO):

        # Usa las diferencias del sensor que necesita, ya sea al abrir o cerrar
        difAct = difActSensA if estado == ABRIENDO else difActSensC
        difAnt = difAntSensA if estado == ABRIENDO else difAntSensC

        # En la primer lectura, difAnt = 0 pero difAct > 0, por lo que activará el estado obstruido.
        # Para evitar esto, no se realiza la verificación en la primer lectura. Esto se puede hacer
        # sin vulnerar el mecanismo de seguridad ya que antes de iniciar el movimiento verifica
        # si hay obstrucciones.
        if (difAnt > 0 and difAct > difAnt * FACTOR_DIFERENCIA):
            releMotorA.value(0)
            releMotorC.value(0)
            estado = OBSTRUIDO
            print(estado)

    # Manejo de obstrucciones
    if (estado == OBSTRUIDO):

        if (comando == CERRAR and distSensC > DIST_DETECCION_OBSTRUCCION):
            releMotorC.value(1)
            estado = CERRANDO
            print(estado)

        if (comando == ABRIR and distSensA > DIST_DETECCION_OBSTRUCCION):
            releMotorA.value(1)
            estado = ABRIENDO
            print(estado)

    difAntSensA = difActSensA
    difAntSensC = difActSensC

def manejarAperturaCierre (distSensA, distSensC):
    global estado
    global tEstatico

    # Funcionalidad base de apertura y cierre
    if (estado == ABIERTO and comando == CERRAR and distSensA < DIST_DETECCION_PORTON):
        
        if (distSensC > DIST_DETECCION_OBSTRUCCION):
            estado = CERRANDO
            releMotorC.value(1)
        else:
            releMotorC.value(0)
            estado = OBSTRUIDO

        print(estado)

    if (estado == CERRADO and comando == ABRIR and distSensC < DIST_DETECCION_PORTON):

        if (distSensA > DIST_DETECCION_OBSTRUCCION):
            estado = ABRIENDO
            releMotorA.value(1)
        else:
            releMotorA.value(0)
            estado = OBSTRUIDO
            
        print(estado)

    # Fin del recorrido
    if (estado == ABRIENDO and distSensA < DIST_DETECCION_PORTON):
        releMotorA.value(0)
        estado = ABIERTO
        tEstatico = 0
        print(estado)

    if (estado == CERRANDO and distSensC < DIST_DETECCION_PORTON):
        releMotorC.value(0)
        estado = CERRADO
        tEstatico = 0
        print(estado)

def calcularEstadoGuardado ():

    global comando 

    distSensA = round(sensorA.distance_cm())
    distSensC = round(sensorC.distance_cm())
    estado = None

    # Si detecta el porton en las posiciones de apertura o cierre, ya asigna el estado
    if (distSensA < DIST_DETECCION_PORTON):
        estado = ABIERTO

    elif (distSensC < DIST_DETECCION_PORTON):
        estado = CERRADO

    # Si no esta en las posiciones de cierre pero se detecta una obstrucción, se asigna el estado
    # y se asigna el comando de cierre por defecto (no se puede obtener el último valor del tópico,
    # el broker MQTT no lo reenvía al suscribirse).
    elif (distSensC < DIST_DETECCION_OBSTRUCCION):
        comando = CERRAR
        estado = OBSTRUIDO

    # Si queda en el medio pero no esta obstruido, intenta cerrarse por defecto.
    else:
        comando = CERRAR
        estado = CERRANDO
        releMotorC.value(1)

    return estado

def calcularEstadoActual (distSensA, distSensC, distAntSensA, distAntSensC):
    manejarFallaMecanica (distSensA, distSensC, distAntSensA, distAntSensC)
    manejarObstruccion (distSensA, distSensC, distAntSensA, distAntSensC)
    manejarAperturaCierre (distSensA, distSensC) 

def asignarColorDeEstado (estado):
    color = ""

    if estado == OBSTRUIDO or estado == FALLA_MECANICA:
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
        color = "#323232"
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


# Le da un valor inicial al estado, ya que broker MQTT no envía el ultimo estado guardado.
estado = calcularEstadoGuardado()

while estado != FALLA_MECANICA:
    time.sleep_ms(1000)

    try:
        conexionMQTT.check_msg()

        distSensA = round(sensorA.distance_cm())
        distSensC = round(sensorC.distance_cm())

        calcularEstadoActual(distSensA, distSensC, distAntSensA, distAntSensC)

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

        distAntSensA = distSensA
        distAntSensC = distSensC

    except OSError as e:
        print("Error de conexion: ", e)
        time.sleep(5)
        machine.reset()
