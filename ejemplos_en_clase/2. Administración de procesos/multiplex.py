#!/usr/bin/python3
import threading
import time
import random

multijugador = threading.Semaphore(4)
dentro = []
mut_dentro = threading.Semaphore(1)

def paralelo(num):
    print(f'{num}: Nace el hilo')
    multijugador.acquire()
    with mut_dentro:
        dentro.append(num)
    print(f'{dentro}: Entrando')
    time.sleep(random.random())
    print(f'{dentro}: Saliendo')
    with mut_dentro:
        dentro.remove(num)
    multijugador.release()

for i in range(10):
    threading.Thread(target=paralelo, args=[i]).start()

#   Azucar sintáctico
