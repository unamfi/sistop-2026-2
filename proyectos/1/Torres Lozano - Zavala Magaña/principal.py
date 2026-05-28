# AUTORES:
# Luis Arturo Zavala Magaña - 321045182
# Luis Torres Lozano - 318209636
# Facultad de Ingeniería
# Uiversidad Nacional Autónoma de México

"""
principal.py — Punto de entrada del programa FiUnamFS

Uso:
    python principal.py <ruta_a_fiunamfs.img>

Ejemplo:
    python principal.py ./fiunamfs.img

El programa tiene 5 hilos que se coordinan con semáforos:
  _menu           → muestra el menú y le avisa al hilo correcto qué hacer
  _listar         → lista los archivos del directorio
  _copiar_a_local → copia un archivo de FiUnamFS a la computadora
  _copiar_a_fs    → copia un archivo de la computadora a FiUnamFS
  _eliminar       → elimina un archivo de FiUnamFS

Cómo funciona la sincronización:
  Cada hilo operativo tiene un semáforo inicializado en 0 (bloqueado).
  El hilo _menu tiene su propio semáforo inicializado en 1 (activo).

  1. _menu adquiere su semáforo y muestra las opciones.
  2. El usuario elige una opción.
  3. _menu libera el semáforo del hilo elegido lo despierta.
  4. Ese hilo ejecuta su tarea y al terminar libera el semáforo del menú.
  5. El ciclo se repite.

  Con esto garantizamos que nunca haya dos operaciones corriendo al mismo
  tiempo y que el menú no aparezca mientras algo está en proceso.
"""

import sys
import threading

from sistema_archivos import FiUnamFS, validar_imagen
from utilidades import (
    limpiar_pantalla, imprimir_encabezado,
    imprimir_exito, imprimir_error, imprimir_info, formatear_tamano
)

# Guardamos la opción elegida como variable global para que todos los hilos
# puedan leerla y saber si deben terminar cuando el usuario elige salir.
opcion: str = ""
fs: FiUnamFS | None = None


def _menu(sem_menu, sem_listar, sem_local, sem_fs, sem_eliminar):
    """
    Hilo del menú. Muestra las opciones y despierta al hilo correspondiente.

    sem_menu arranca en 1 para que el menú aparezca de inmediato al iniciar.
    Los demás semáforos arrancan en 0 y se liberan según lo que elija el usuario.
    """
    global opcion

    while True:
        sem_menu.acquire()
        limpiar_pantalla()
        imprimir_encabezado("Menú Principal")
        print("  (1) Listar archivos del directorio")
        print("  (2) Copiar archivo desde FiUnamFS a mi computadora")
        print("  (3) Copiar archivo desde mi computadora a FiUnamFS")
        print("  (4) Eliminar un archivo de FiUnamFS")
        print("  (5) Salir\n")
        opcion = input("  Opción → ").strip()

        if   opcion == "1": sem_listar.release()
        elif opcion == "2": sem_local.release()
        elif opcion == "3": sem_fs.release()
        elif opcion == "4": sem_eliminar.release()
        elif opcion == "5":
            # Al salir hay que despertar a todos los hilos para que
            # puedan revisar la opción y terminar su bucle
            sem_listar.release()
            sem_local.release()
            sem_fs.release()
            sem_eliminar.release()
            break
        else:
            imprimir_error("  Opción no válida.")
            sem_menu.release()  # Volvemos a mostrar el menú


def _listar(sem_menu, sem_listar):
    """Hilo que lista los archivos del directorio de FiUnamFS."""
    global opcion, fs

    while True:
        sem_listar.acquire()
        if opcion == "5":
            break

        limpiar_pantalla()
        imprimir_encabezado("Archivos en FiUnamFS")

        archivos = fs.listar_archivos()
        if not archivos:
            imprimir_info("  El directorio está vacío.")
        else:
            print(f"  {'#':<4} {'Nombre':<16} {'Tamaño':>10}   {'Creación'}")
            print(f"  {'─'*4} {'─'*16} {'─'*10}   {'─'*19}")
            for i, archivo in enumerate(archivos, 1):
                print(f"  {i:<4} {archivo.name:<16} {formatear_tamano(archivo.size):>10}   {archivo.creation_date}")

        input("\n  Presiona Enter para continuar...")
        sem_menu.release()


def _copiar_a_local(sem_menu, sem_local):
    """Hilo que copia un archivo de FiUnamFS hacia la computadora."""
    global opcion, fs

    while True:
        sem_local.acquire()
        if opcion == "5":
            break

        limpiar_pantalla()
        imprimir_encabezado("Copiar FiUnamFS → Mi Computadora")

        nombre_archivo     = input("  Nombre del archivo en FiUnamFS: ").strip()
        directorio_destino = input("  Directorio destino (ej. C:\\Users\\usuario\\Descargas): ").strip()

        resultado = fs.copiar_a_local(nombre_archivo, directorio_destino)
        if resultado.startswith("[OK]"):
            imprimir_exito(f"\n  {resultado}")
        else:
            imprimir_error(f"\n  {resultado}")

        input("\n  Presiona Enter para continuar...")
        sem_menu.release()


def _copiar_a_fs(sem_menu, sem_fs):
    """Hilo que copia un archivo de la computadora hacia FiUnamFS."""
    global opcion, fs

    while True:
        sem_fs.acquire()
        if opcion == "5":
            break

        limpiar_pantalla()
        imprimir_encabezado("Copiar Mi Computadora → FiUnamFS")
        imprimir_info("  Incluye la extensión, por ejemplo: C:\\Users\\usuario\\foto.jpg\n")

        ruta_origen = input("  Ruta del archivo a copiar: ").strip()

        resultado = fs.copiar_desde_local(ruta_origen)
        if resultado.startswith("[OK]"):
            imprimir_exito(f"\n  {resultado}")
        else:
            imprimir_error(f"\n  {resultado}")

        input("\n  Presiona Enter para continuar...")
        sem_menu.release()


def _eliminar(sem_menu, sem_eliminar):
    """Hilo que elimina un archivo del directorio de FiUnamFS."""
    global opcion, fs

    while True:
        sem_eliminar.acquire()
        if opcion == "5":
            break

        limpiar_pantalla()
        imprimir_encabezado("Eliminar Archivo de FiUnamFS")

        nombre_archivo = input("  Nombre del archivo a eliminar: ").strip()
        confirmacion   = input(f'  ¿Seguro que deseas eliminar "{nombre_archivo}"? (s/n): ').strip().lower()

        if confirmacion == "s":
            resultado = fs.eliminar_archivo(nombre_archivo)
            if resultado.startswith("[OK]"):
                imprimir_exito(f"\n  {resultado}")
            else:
                imprimir_error(f"\n  {resultado}")
        else:
            imprimir_info("\n  Operación cancelada.")

        input("\n  Presiona Enter para continuar...")
        sem_menu.release()


def main():
    global fs

    if len(sys.argv) != 2:
        imprimir_error("Uso: python principal.py <ruta_a_fiunamfs.img>")
        sys.exit(1)

    ruta_imagen = sys.argv[1]

    # Validaos antes de hacer cualquier cosa — no queremos tocar un archivo
    # que no sea un FiUnamFS válido y terminar alterando datos que no debiamos
    if not validar_imagen(ruta_imagen):
        imprimir_error(f'El archivo "{ruta_imagen}" no es una imagen FiUnamFS válida.')
        sys.exit(1)

    fs = FiUnamFS(ruta_imagen)

    # sem_menu arranca en 1 para que el menú aparezca de inmediato.
    # Los demás arrancan en 0 y esperan a que el menú los despierte.
    sem_menu     = threading.Semaphore(1)
    sem_listar   = threading.Semaphore(0)
    sem_local    = threading.Semaphore(0)
    sem_fs       = threading.Semaphore(0)
    sem_eliminar = threading.Semaphore(0)

    hilos = [
        threading.Thread(target=_menu,          args=(sem_menu, sem_listar, sem_local, sem_fs, sem_eliminar), daemon=True),
        threading.Thread(target=_listar,        args=(sem_menu, sem_listar),   daemon=True),
        threading.Thread(target=_copiar_a_local,args=(sem_menu, sem_local),    daemon=True),
        threading.Thread(target=_copiar_a_fs,   args=(sem_menu, sem_fs),       daemon=True),
        threading.Thread(target=_eliminar,      args=(sem_menu, sem_eliminar), daemon=True),
    ]

    for hilo in hilos:
        hilo.start()

    # Esperamos a que el hilo del menú termine (cuando el usuario elige salir)
    hilos[0].join()
    imprimir_info("\n  ¡Hasta luego!\n")


if __name__ == "__main__":
    main()
