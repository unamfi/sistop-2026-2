import os

from .exceptions import DiskError

DISK_SIZE = 1_474_560
CLUSTER_SIZE = 2048
SECTOR_SIZE = 512
SECTORS_PER_CLUSTER = 4


class FiUnamFSDisk:
    def __init__(self, path: str) -> None:
        if not os.path.exists(path):
            raise DiskError(f"Imagen no encontrada: {path}")
        actual = os.path.getsize(path)
        if actual != DISK_SIZE:
            raise DiskError(
                f"Imagen inválida: {actual} B (se esperan {DISK_SIZE} B)"
            )
        # 'r+b' preserva el contenido; 'wb' lo destruiría
        self._fh = open(path, 'r+b')

    @staticmethod
    def cluster_offset(cluster_num: int) -> int:
        return cluster_num * CLUSTER_SIZE

    def read_cluster(self, cluster_num: int) -> bytes:
        self._fh.seek(self.cluster_offset(cluster_num))
        data = self._fh.read(CLUSTER_SIZE)
        if len(data) != CLUSTER_SIZE:
            raise DiskError(f"Lectura incompleta en cluster {cluster_num}")
        return data

    def write_cluster(self, cluster_num: int, data: bytes) -> None:
        if len(data) != CLUSTER_SIZE:
            raise DiskError(
                f"Cluster {cluster_num}: datos de {len(data)} B "
                f"(se esperan {CLUSTER_SIZE} B)"
            )
        self._fh.seek(self.cluster_offset(cluster_num))
        self._fh.write(data)
        self._fh.flush()

    def read_bytes(self, offset: int, length: int) -> bytes:
        self._fh.seek(offset)
        return self._fh.read(length)

    def write_bytes(self, offset: int, data: bytes) -> None:
        self._fh.seek(offset)
        self._fh.write(data)
        self._fh.flush()

    def close(self) -> None:
        if self._fh and not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> 'FiUnamFSDisk':
        return self

    def __exit__(self, *_) -> None:
        self.close()
