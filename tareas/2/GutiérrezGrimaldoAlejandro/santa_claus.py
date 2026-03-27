import random
import threading
import time

# Parametros base de la simulacion
NUM_ELFOS = 10
NUM_RENOS = 9
DURACION = 20  # segundos

# Semaforos de coordinacion principal
sem_santa = threading.Semaphore(0)
sem_renos = threading.Semaphore(0)
sem_elfos = threading.Semaphore(0)

# Semaforos para proteger datos compartidos
sem_cont_renos = threading.Semaphore(1)
sem_cont_elfos = threading.Semaphore(1)
sem_print = threading.Semaphore(1)
sem_stats = threading.Semaphore(1)

# Estado global de la simulacion
renos_de_vuelta = 0
elfos_en_espera = 0
ayudas_elfos = 0
viajes_renos = 0
corriendo = True


def log(quien, msg):
    with sem_print:
        print(f"[{quien}] {msg}")


def santa():
    global renos_de_vuelta, elfos_en_espera, ayudas_elfos, viajes_renos

    log("SANTA", "me duermo")

    while corriendo:
        # Santa se bloquea aqui hasta que renos o elfos lo despierten
        sem_santa.acquire()
        if not corriendo:
            break

        atendio_renos = False

        # Prioridad 1: atender renos cuando regresan los 9
        sem_cont_renos.acquire()
        if renos_de_vuelta == NUM_RENOS:
            atendio_renos = True
            log("SANTA", "estan los 9 renos, preparo salida")
            time.sleep(random.uniform(0.4, 1.0))
            renos_de_vuelta = 0
            sem_stats.acquire()
            viajes_renos += 1
            sem_stats.release()
            for _ in range(NUM_RENOS):
                sem_renos.release()
        sem_cont_renos.release()

        # Prioridad 2: atender el grupo de 3 elfos
        sem_cont_elfos.acquire()
        if (not atendio_renos) and elfos_en_espera == 3:
            log("SANTA", "atiendo 3 elfos")
            time.sleep(random.uniform(0.2, 0.6))
            elfos_en_espera = 0
            sem_stats.acquire()
            ayudas_elfos += 1
            sem_stats.release()
            for _ in range(3):
                sem_elfos.release()
        sem_cont_elfos.release()

        if corriendo:
            log("SANTA", "vuelvo a dormir")


def reno(n):
    global renos_de_vuelta

    while corriendo:
        time.sleep(random.uniform(2.0, 5.0))
        if not corriendo:
            break

        # Cada reno marca su regreso y el noveno despierta a Santa
        sem_cont_renos.acquire()
        renos_de_vuelta += 1
        log(f"RENO {n}", f"llegue ({renos_de_vuelta}/{NUM_RENOS})")
        if renos_de_vuelta == NUM_RENOS:
            log(f"RENO {n}", "somos todos, despierto a Santa")
            sem_santa.release()
        sem_cont_renos.release()

        sem_renos.acquire()
        if not corriendo:
            break
        log(f"RENO {n}", "termina el viaje")


def elfo(n):
    global elfos_en_espera

    while corriendo:
        time.sleep(random.uniform(1.0, 3.0))
        if not corriendo:
            break

        log(f"ELFO {n}", "tengo una duda")

        # Solo se permite un grupo de 3 elfos esperando ayuda
        entro_al_grupo = False
        sem_cont_elfos.acquire()
        if elfos_en_espera < 3:
            elfos_en_espera += 1
            entro_al_grupo = True
            log(f"ELFO {n}", f"esperando grupo ({elfos_en_espera}/3)")
            if elfos_en_espera == 3:
                log(f"ELFO {n}", "ya somos 3, despierto a Santa")
                sem_santa.release()
        sem_cont_elfos.release()

        if not entro_al_grupo:
            log(f"ELFO {n}", "ya hay 3 esperando, sigo trabajando")
            continue

        sem_elfos.acquire()
        if not corriendo:
            break
        log(f"ELFO {n}", "Santa resolvio mi duda")


def asist_contador():
    global ayudas_elfos, viajes_renos

    while corriendo:
        time.sleep(5)
        if not corriendo:
            break
        # Reporte periodico simple
        sem_stats.acquire()
        ayudas = ayudas_elfos
        viajes = viajes_renos
        sem_stats.release()
        log("REPORTE", f"grupos de elfos atendidos={ayudas}, viajes de renos={viajes}")


def pedir_entero(mensaje, valor_default):
    # Si la entrada no es valida, se usa el valor default
    texto = input(mensaje).strip()
    if texto == "":
        return valor_default
    try:
        valor = int(texto)
        if valor < 1:
            return valor_default
        return valor
    except ValueError:
        return valor_default


def pedir_datos():
    print("Configura el problema (Enter para valor default)")
    elfos = pedir_entero(f"Cantidad de elfos [{NUM_ELFOS}]: ", NUM_ELFOS)
    duracion = pedir_entero(f"Duracion en segundos [{DURACION}]: ", DURACION)
    print("")
    return elfos, duracion


def mostrar_inicio(cant_elfos, duracion):
    print("Problema de Santa Claus")
    print(f"Alejandro Gutiérrez Grimaldo")
    print(f"Sistemas Operativos")
    print(f"FI-UNAM")
    print(f"Renos: {NUM_RENOS} | Elfos: {cant_elfos} | Duracion: {duracion}s")
    print("Iniciando hilos...\n")


def main():
    global corriendo
    cant_elfos, duracion = pedir_datos()
    mostrar_inicio(cant_elfos, duracion)

    # Se crea un hilo por rol
    hilos = []
    hilos.append(threading.Thread(target=santa))
    hilos.append(threading.Thread(target=asist_contador))

    for i in range(1, NUM_RENOS + 1):
        hilos.append(threading.Thread(target=reno, args=(i,)))

    for i in range(1, cant_elfos + 1):
        hilos.append(threading.Thread(target=elfo, args=(i,)))

    for h in hilos:
        h.start()

    # Corre la simulacion durante el tiempo solicitado
    time.sleep(duracion)
    corriendo = False

    # Desbloqueo final para que todos los hilos puedan terminar
    sem_santa.release()
    for _ in range(NUM_RENOS):
        sem_renos.release()
    for _ in range(cant_elfos):
        sem_elfos.release()

    for h in hilos:
        h.join(timeout=2)

    sem_stats.acquire()
    ayudas = ayudas_elfos
    viajes = viajes_renos
    sem_stats.release()
    print(f"\nPrograma finalizado. grupos_elfos={ayudas}, viajes_renos={viajes}")


if __name__ == "__main__":
    main()