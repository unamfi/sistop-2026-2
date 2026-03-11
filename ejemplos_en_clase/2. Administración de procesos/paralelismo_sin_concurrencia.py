#!/usr/bin/python3
import threading
import time
import random

resultados = [None for i in range(100)]
hilos = []

def inicializar(n):
    global resultados
    azar = random.random()
    time.sleep(0.1)
    resultados[n] = azar

for i in range(100):
    hilos.append(threading.Thread(target = inicializar, args = [i]))

for i in hilos:
    i.start()

for i in hilos:
    i.join()

print(resultados)
