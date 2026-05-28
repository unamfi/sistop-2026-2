import sys
import struct
import threading
from queue import Queue
from datetime import datetime

CLUSTER_SIZE = 2048
ENTRY_SIZE = 64
DIRECTORY_CLUSTERS = range(1, 9)
DATA_START_CLUSTER = 9

# 🔒 Lock para proteger acceso al disco
disk_lock = threading.Lock()

# 📦 Cola para comunicación entre hilos
log_queue = Queue()


# =========================
# FUNCIONES DEL SISTEMA
# =========================

def ls(disk_path):
    with disk_lock:
        with open(disk_path, "rb") as f:
            found = False
            for cluster in DIRECTORY_CLUSTERS:
                f.seek(cluster * CLUSTER_SIZE)
                data = f.read(CLUSTER_SIZE)

                for i in range(0, CLUSTER_SIZE, ENTRY_SIZE):
                    entry = data[i:i+ENTRY_SIZE]
                    tipo = chr(entry[0])

                    if tipo == '-':
                        found = True
                        nombre = entry[1:16].decode("ascii").rstrip("\x00").strip()
                        size = struct.unpack("<I", entry[16:20])[0]
                        start_cluster = struct.unpack("<I", entry[20:24])[0]
                        print(f"{nombre} | {size} bytes | cluster {start_cluster}")

            if not found:
                print("Fin del listado.")


def find_free_directory_entry(f):
    for cluster in DIRECTORY_CLUSTERS:
        f.seek(cluster * CLUSTER_SIZE)
        data = bytearray(f.read(CLUSTER_SIZE))

        for i in range(0, CLUSTER_SIZE, ENTRY_SIZE):
            if data[i] == ord('/'):
                return cluster, i
    return None, None


def copyin(disk_path, filename):
    with open(filename, "rb") as src:
        content = src.read()

    size = len(content)
    needed_clusters = (size + CLUSTER_SIZE - 1) // CLUSTER_SIZE

    with disk_lock:
        with open(disk_path, "r+b") as f:
            cluster = DATA_START_CLUSTER
            f.seek(cluster * CLUSTER_SIZE)
            f.write(content.ljust(needed_clusters * CLUSTER_SIZE, b'\x00'))

            dir_cluster, offset = find_free_directory_entry(f)

            if dir_cluster is None:
                print("Directorio lleno")
                return

            f.seek(dir_cluster * CLUSTER_SIZE + offset)

            entry = bytearray(ENTRY_SIZE)
            entry[0] = ord('-')
            entry[1:1+len(filename)] = filename.encode("ascii")
            entry[16:20] = struct.pack("<I", size)
            entry[20:24] = struct.pack("<I", cluster)

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S").encode("ascii")
            entry[24:24+14] = timestamp
            entry[38:38+14] = timestamp

            f.write(entry)

    print("Archivo copiado correctamente.")


def copyout(disk_path, filename):
    with disk_lock:
        with open(disk_path, "rb") as f:
            for cluster in DIRECTORY_CLUSTERS:
                f.seek(cluster * CLUSTER_SIZE)
                data = f.read(CLUSTER_SIZE)

                for i in range(0, CLUSTER_SIZE, ENTRY_SIZE):
                    entry = data[i:i+ENTRY_SIZE]
                    tipo = chr(entry[0])

                    if tipo == '-':
                        nombre = entry[1:16].decode("ascii").rstrip("\x00").strip()

                        if nombre == filename:
                            size = struct.unpack("<I", entry[16:20])[0]
                            start_cluster = struct.unpack("<I", entry[20:24])[0]

                            f.seek(start_cluster * CLUSTER_SIZE)
                            content = f.read(size)

                            with open("copiado_" + filename, "wb") as out:
                                out.write(content)

                            print("Archivo extraído correctamente.")
                            return

    print("Archivo no encontrado.")


def rm(disk_path, filename):
    with disk_lock:
        with open(disk_path, "r+b") as f:
            for cluster in DIRECTORY_CLUSTERS:
                f.seek(cluster * CLUSTER_SIZE)
                data = bytearray(f.read(CLUSTER_SIZE))

                for i in range(0, CLUSTER_SIZE, ENTRY_SIZE):
                    entry = data[i:i+ENTRY_SIZE]
                    tipo = chr(entry[0])

                    if tipo == '-':
                        nombre = entry[1:16].decode("ascii").rstrip("\x00").strip()

                        if nombre == filename:
                            data[i] = ord('/')
                            f.seek(cluster * CLUSTER_SIZE)
                            f.write(data)

                            print("Archivo eliminado correctamente.")
                            return

    print("Archivo no encontrado.")


# =========================
# HILOS
# =========================

def worker(command, disk, filename=None):
    log_queue.put(f"Iniciando comando: {command}")

    if command == "ls":
        ls(disk)
    elif command == "copyin":
        copyin(disk, filename)
    elif command == "copyout":
        copyout(disk, filename)
    elif command == "rm":
        rm(disk, filename)

    log_queue.put(f"Comando terminado: {command}")


def logger():
    while True:
        mensaje = log_queue.get()
        if mensaje == "STOP":
            break
        print(f"[LOG] {mensaje}")
        log_queue.task_done()


# =========================
# MAIN
# =========================

def main():
    if len(sys.argv) < 3:
        print("Uso:")
        print("python main.py ls fiunamfs.img")
        print("python main.py copyin fiunamfs.img archivo.txt")
        print("python main.py copyout fiunamfs.img archivo.txt")
        print("python main.py rm fiunamfs.img archivo.txt")
        return

    command = sys.argv[1]
    disk = sys.argv[2]
    filename = sys.argv[3] if len(sys.argv) == 4 else None

    log_thread = threading.Thread(target=logger)
    log_thread.start()

    worker_thread = threading.Thread(target=worker, args=(command, disk, filename))
    worker_thread.start()

    worker_thread.join()

    log_queue.put("STOP")
    log_thread.join()


if __name__ == "__main__":
    main()