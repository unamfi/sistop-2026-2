from fiunamfs import FiUnamFS
from threads import iniciar_logger

fs = FiUnamFS("fiunamfs.img")
iniciar_logger()

while True:

    print("\n=== FiUnamFS ===")
    print("1. Listar archivos")
    print("2. Copiar archivo desde FiUnamFS")
    print("3. Eliminar archivo")
    print("4. Copiar hacia FiUnamFS")
    print("5. Salir")

    opcion = input("\nOpción: ")

    if opcion == "1":
        fs.mostrar_archivos()

    elif opcion == "2":
        fs.copiar_desde_fs()

    elif opcion == "3":
        fs.eliminar_archivo()

    elif opcion == "4":
        fs.copiar_hacia_fs()

    elif opcion == "5":
        break

    else:
        print("\nOpción inválida")