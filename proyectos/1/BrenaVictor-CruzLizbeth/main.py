"""
Proyecto micro Sistema de Archivos
Autores:
    Brena de León Vícctor JAvier
    Cruz Manríquez Lizbeth

Punto de Entrada Principal y Orquestador de Concurrencia (Main).

Este script realiza la inicialización de los hilos de ejecución concurrentes y los
mecanismos de exclusión mutua global. Configura y monta el daemon del sistema de archivos 
en espacio de usuario (FUSE) delegando las peticiones de I/O al pool multihilo del kernel.

Uso:
    python3 main.py <punto_montaje>
"""

import sys
import threading
import time
import fuse

fuse.fuse_python_api = (0, 2)
# Importación local de los componentes
from fiunamfs import FiUnamFS, DISK_FILE
from fuse_interface import FiUnamFSFuse

# SECCIÓN DE CONCURRENCIA Y COMUNICACIÓN ENTRE HILOS
# Candado reentrante (RLock) compartido globalmente. Previene condiciones de carrera 
# protegiendo el acceso simultáneo al descriptor binario de disco por parte de los hilos de FUSE.
fs_lock = threading.RLock()
operation_log = []

def log_operation(message):
    """Inserta de manera segura un evento de estado en la cola compartida."""
    with fs_lock:
        operation_log.append(message)

def monitor_thread():
    """Hilo Monitor.
    
    Representa el segundo hilo de ejecución. 
    Despierta periódicamente, adquiere el candado global, extrae de forma segura las trazas 
    almacenadas por los hilos de FUSE y las despliega en la salida de error estándar (sys.stderr), 
    mitigando efectos secundarios de retraso de búfer en terminal.
    """
    while True:
        with fs_lock:
            if operation_log:
                msg = operation_log.pop(0)
                print(f"[MONITOR] {msg}", file=sys.stderr, flush=True)
        time.sleep(0.2)

def main():
    """Valida argumentos de entrada, arranca hilos secundarios y lanza el servidor FUSE."""
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <punto_montaje>")
        sys.exit(1)

    # Inyección forzada de la bandera '-f' (Foreground) para retener el ciclo de vida 
    # del proceso en primer plano, permitiendo observar las impresiones por el monitor.
    if "-f" not in sys.argv:
        sys.argv.insert(1, "-f")

    # Inicialización e inicio inmediato del Hilo Monitor Independiente
    monitor = threading.Thread(target=monitor_thread, daemon=True)
    monitor.start()

    # Inicialización del Driver Binario
    fiunam = FiUnamFS(DISK_FILE, fs_lock, log_operation)
    
    # Configuración de la capa de interfaz FUSE
    server = FiUnamFSFuse(
        fiunam,
        fs_lock,
        log_operation,
        version="%prog " + fuse.__version__,
        usage="\nFiUnamFS - Proyecto Sistemas Operativos\n"
    )

    # El parser de FUSE procesará de forma segura las banderas nativas desde sys.argv 
    # y habilitará la ejecución multihilo concurrente administrada por el núcleo.
    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()