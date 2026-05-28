import struct
import threading


class FiUnamFS:

    def __init__(self, image_path):
        self.image_path = image_path
        self.file = None
        self.lock = threading.Lock()

    def open_fs(self):

        try:
            self.file = open(self.image_path, "r+b")
            print("[OK] Archivo de sistema abierto correctamente")

        except FileNotFoundError:
            print("[ERROR] No se encontró el archivo .img")

    def read_superblock(self):

        if not self.file:
            print("[ERROR] El sistema no está abierto")
            return

        self.file.seek(5)
        fs_name = self.file.read(8).decode("ascii").strip('\x00')

        self.file.seek(14)
        version = self.file.read(4).decode("ascii").strip('\x00')

        self.file.seek(20)
        volume_label = self.file.read(16).decode("ascii").strip('\x00')

        self.file.seek(40)
        cluster_size = struct.unpack('<I', self.file.read(4))[0]

        self.file.seek(50)
        dir_clusters = struct.unpack('<I', self.file.read(4))[0]

        self.file.seek(60)
        total_clusters = struct.unpack('<I', self.file.read(4))[0]

        print("\n====== SUPERBLOQUE ======")
        print(f"Sistema de archivos : {fs_name}")
        print(f"Versión             : {version}")
        print(f"Etiqueta volumen    : {volume_label}")
        print(f"Tamaño cluster      : {cluster_size} bytes")
        print(f"Clusters directorio : {dir_clusters}")
        print(f"Clusters totales    : {total_clusters}")
        print("=========================\n")

    def list_directory(self):

        with self.lock:

            if not self.file:
                print("[ERROR] El sistema no está abierto")
                return

            print("\n====== DIRECTORIO ======\n")

            directory_start = 2048
            directory_size = 8 * 2048

            self.file.seek(directory_start)

            entries = directory_size // 64

            for i in range(entries):

                entry = self.file.read(64)

                file_type = entry[0:1].decode("ascii", errors="ignore")

                if file_type == "/" or file_type == "\x00":
                    continue

                filename = (
                    entry[1:16]
                    .decode("ascii", errors="ignore")
                    .replace('\x00', '')
                    .strip()
                )

                filesize = struct.unpack('<I', entry[16:20])[0]

                start_cluster = struct.unpack('<I', entry[20:24])[0]

                print(f"Archivo : {filename}")
                print(f"Tamaño  : {filesize} bytes")
                print(f"Cluster : {start_cluster}")
                print("-------------------------")

    def copy_from_fs(self, target_filename):

        with self.lock:

            if not self.file:
                print("[ERROR] El sistema no está abierto")
                return

            directory_start = 2048
            directory_size = 8 * 2048

            self.file.seek(directory_start)

            entries = directory_size // 64

            for i in range(entries):

                entry = self.file.read(64)

                file_type = entry[0:1].decode("ascii", errors="ignore")

                if file_type == "/" or file_type == "\x00":
                    continue

                filename = (
                    entry[1:16]
                    .decode("ascii", errors="ignore")
                    .replace('\x00', '')
                    .strip()
                )

                filesize = struct.unpack('<I', entry[16:20])[0]

                start_cluster = struct.unpack('<I', entry[20:24])[0]

                if filename == target_filename:

                    print(f"\n[INFO] Copiando {filename}...")

                    data_offset = start_cluster * 2048

                    self.file.seek(data_offset)

                    file_data = self.file.read(filesize)

                    with open(filename, "wb") as output_file:
                        output_file.write(file_data)

                    print(f"[OK] Archivo {filename} copiado correctamente\n")
                    return

            print("[ERROR] Archivo no encontrado")

    def delete_file(self, target_filename):

        with self.lock:

            if not self.file:
                print("[ERROR] El sistema no está abierto")
                return

            directory_start = 2048
            directory_size = 8 * 2048

            self.file.seek(directory_start)

            entries = directory_size // 64

            for i in range(entries):

                entry_position = self.file.tell()

                entry = self.file.read(64)

                file_type = entry[0:1].decode("ascii", errors="ignore")

                if file_type == "/" or file_type == "\x00":
                    continue

                filename = (
                    entry[1:16]
                    .decode("ascii", errors="ignore")
                    .replace('\x00', '')
                    .strip()
                )

                if filename == target_filename:

                    print(f"\n[INFO] Eliminando {filename}...")

                    self.file.seek(entry_position)

                    self.file.write(b'/')

                    print(f"[OK] Archivo {filename} eliminado correctamente\n")
                    return

            print("[ERROR] Archivo no encontrado")

    def close_fs(self):

        if self.file:
            self.file.close()
            print("[OK] Sistema de archivos cerrado")
