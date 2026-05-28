from threading import Thread
from queue import Queue

cola_logs = Queue()

def logger():

    while True:
        mensaje = cola_logs.get()
        print(f"\n>>> [LOG] {mensaje}\n")

def iniciar_logger():
    hilo = Thread(
        target=logger,
        daemon=True
    )
    hilo.start()