#!/usr/bin/python3
import threading
import time
import random

candado = threading.Lock()

def paralelo(num):
    candado.acquire()
    print(f'{num}: Entrando')
    time.sleep(random.random())
    print(f'{num}: Saliendo')
    candado.release()

for i in range(10):
    threading.Thread(target=paralelo, args=[i]).start()

#   Azucar sintáctico
