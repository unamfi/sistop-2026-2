from filesystem import FiUnamFS
from sync_manager import *

import threading


def menu():

    fs = FiUnamFS("fiunamfs.img")

    fs.open_fs()

    while True:

        print("\n========== FiUnamFS ==========")
        print("1. Ver superbloque")
        print("2. Listar directorio")
        print("3. Copiar archivo")
        print("4. Eliminar archivo")
        print("5. Probar concurrencia")
        print("6. Salir")

        option = input("\nSelecciona una opción: ")

        if option == "1":

            fs.read_superblock()

        elif option == "2":

            fs.list_directory()

        elif option == "3":

            filename = input("Archivo a copiar: ")
            fs.copy_from_fs(filename)

        elif option == "4":

            filename = input("Archivo a eliminar: ")
            fs.delete_file(filename)

        elif option == "5":

            monitor_thread = threading.Thread(
                target=directory_monitor,
                args=(fs,)
            )

            copy_thread = threading.Thread(
                target=copy_task,
                args=(fs,)
            )

            monitor_thread.start()
            copy_thread.start()

            monitor_thread.join()
            copy_thread.join()

        elif option == "6":

            fs.close_fs()
            break

        else:

            print("[ERROR] Opción inválida")


menu()
