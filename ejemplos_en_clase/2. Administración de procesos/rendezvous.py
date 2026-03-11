#!/usr/bin/python3
import threading
import time

def funcion_izquierda():
    global sem, num
    print('Estoy esperando al usuario...')
    num = input('Dime un número aleatorio entre 1 y 100...')
    izq_listo.release()
    der_listo.acquire()
    print('La función izquierda continúa... Y termina.')


def funcion_derecha():
    global sem, num
    print('Esperemos cuatro segunditos...')
    time.sleep(4)
    der_listo.release()
    izq_listo.acquire()
    print('Y a mi “hermanita” le dijiste que:')
    print(num)

izq_listo = threading.Semaphore(0)
der_listo = threading.Semaphore(0)
t1 = threading.Thread(target=funcion_izquierda, args=[])
t2 = threading.Thread(target=funcion_derecha, args=[])

t1.start()
t2.start()

t1.join()
t2.join()

print('Bueeeeno, ¡ya terminamos!')
