import struct

CLUSTER_SIZE = 2048

class FiUnamFSError(Exception):
    pass


class Disk:
    def __init__(self, path):
        self.path = path
        self.file = None

    def open(self):
        self.file = open(self.path, "rb+")
        self._validate_superblock()

    def close(self):
        if self.file:
            self.file.close()

    def read_cluster(self, cluster_number):
        offset = cluster_number * CLUSTER_SIZE
        self.file.seek(offset)
        return self.file.read(CLUSTER_SIZE)

    def _validate_superblock(self):
        self.file.seek(0)
        data = self.file.read(CLUSTER_SIZE)

        magic = data[5:13].decode("ascii").strip()
        version = data[14:18].decode("ascii").strip()

        if magic != "FiUnamFS":
            raise FiUnamFSError("Sistema inválido")

        if version != "26-2":
            raise FiUnamFSError("Versión no soportada")