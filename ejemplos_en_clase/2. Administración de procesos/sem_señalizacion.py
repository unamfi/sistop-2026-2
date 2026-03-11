#!/usr/bin/python3
import threading

def genera_datos():
    global sem, num
    print('Vamos a generar un número aleatorio...')
    num = input('Dime un número aleatorio entre 1 y 100...')
    sem.release()

def reporta_datos():
    global sem, num
    print('¡Me muero de ganas por reportar un dato!')
    sem.acquire()
    print('Y el dato que quiero reportar es:')
    print(num)

sem = threading.Semaphore(0)
t1 = threading.Thread(target=genera_datos, args=[])
t2 = threading.Thread(target=reporta_datos, args=[])

t1.start()
t2.start()

t1.join()
t2.join()

print('Bueeeeno, ¡ya terminamos!')
