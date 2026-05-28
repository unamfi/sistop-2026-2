# main.py
# Punto de entrada del programa FiUnamFS.

import sys

from fiunamfs import FiUnamFS
from monitor import Monitor

AYUDA = """
Manual de Uso:
  python/python3 main.py <img> list
      Lista los archivos en FiUnamFS.

  python/python3 main.py <img> extract <archivo> [salida]
      Copia un archivo de FiUnamFS a tu sistema.
        <archivo>  Nombre del archivo dentro de FiUnamFS
        [salida]   Ruta de destino local  (opcional, default: mismo nombre)

  python/python3 main.py <img> paste <local> [destino]
      Copia un archivo de tu sistema a FiUnamFS.
        <local>    Ruta al archivo en tu sistema
        [destino]  Nombre dentro de FiUnamFS     (opcional, default: mismo nombre)

  python/python3 main.py <img> delete <archivo>
      Elimina un archivo de FiUnamFS.
        <archivo>  Nombre dentro de FiUnamFS

Ejemplos:
  python main.py fiunamfs.img list
  python3 main.py fiunamfs.img extract prueba.txt
  python3 main.py fiunamfs.img extract prueba.txt copia_local.txt
  python main.py fiunamfs.img paste "/home/user/doc.pdf" DOC.PDF
  python3 main.py fiunamfs.img delete viejo.txt
"""


def ejecutar(fs: FiUnamFS, monitor: Monitor, operacion: str, args: list) -> bool:
    # Ejecuta y asigna la operación al método correspondiente de FiUnamFS
    # y notifica al monitor si la operación modifica el disco.

    # Args:
        # fs: Instancia de la clase FiUnamFS.
        # monitor: Instancia del Monitor.
        # operacion: Nombre de la operación ('list', 'extract', 'paste', 'delete').
        # args: Argumentos adicionales de la operación.
    # Returns:
        # Devuelve un booleano: True si la operación se completó sin errores.
    
    if operacion == 'list':
        fs.listar()
        return True

    elif operacion == 'extract':
        if not args:
            print("Error: 'extract' requiere el nombre del archivo.")
            print("  Uso: python main.py <img> extract <archivo> [salida]")
            return False
        salida = args[1] if len(args) > 1 else None
        resultado = fs.extraer(args[0], salida)
        if resultado is not False:
            return True
        else:
            return False

    elif operacion == 'paste':
        if not args:
            print("Error: 'paste' requiere la ruta del archivo local.")
            print("  Uso: python main.py <img> paste <local> [destino]")
            return False
        destino = args[1] if len(args) > 1 else None
        resultado = fs.pegar(args[0], destino)
        if resultado:
            monitor.notificar('paste')   # despierta al monitor solo si hubo cambio
        return resultado

    elif operacion == 'delete':
        if not args:
            print("Error: 'delete' requiere el nombre del archivo.")
            print("  Uso: python main.py <img> delete <archivo>")
            return False
        resultado = fs.borrar(args[0])
        if resultado:
            monitor.notificar('delete')  # despierta al monitor solo si hubo cambio
        return resultado

    else:
        print(f"Operación desconocida: '{operacion}'")
        print(AYUDA)
        return False


def main():
    if len(sys.argv) < 3:
        print(AYUDA)
        sys.exit(1)

    img_path  = sys.argv[1]
    operacion = sys.argv[2].lower()
    args      = sys.argv[3:]

    # Inicialización de las operaciones
    try:
        fs = FiUnamFS(img_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Inicializar y arrancar el monitor en su propio hilo
    monitor = Monitor(fs)
    monitor.iniciar()

    # El hilo principal ejecuta la operación pedida
    exito = ejecutar(fs, monitor, operacion, args)

    # Apagar el monitor limpiamente antes de salir
    monitor.detener()

    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()