import math
import struct
from datetime import datetime

from .disk import CLUSTER_SIZE, FiUnamFSDisk
from .exceptions import DirectoryError
from .superblock import Superblock

# Distribución binaria de 64 bytes por entrada de directorio.
# '<': little-endian | 1s: tipo (b'-' activo / b'/' libre) | 15s: nombre
# II: tamaño y cluster inicial (uint32 c/u) | 6x: relleno | 14s: ctime | 6x | 14s: mtime
_ENTRY_FMT = '<1s15sII6x14s6x14s'
ENTRY_SIZE = struct.calcsize(_ENTRY_FMT)   # == 64

_TYPE_FILE = b'-'   # 0x2d — entrada activa
_TYPE_FREE = b'/'   # 0x2f — entrada disponible
_EMPTY_NAME = b'###############'   # 15 almohadillas

_DATE_FMT = '%Y%m%d%H%M%S'


class DirectoryEntry:
    def __init__(
        self,
        index: int,
        file_type: bytes,
        raw_name: bytes,
        size: int,
        start_cluster: int,
        created_at: str,
        modified_at: str,
    ) -> None:
        self.index = index
        self._file_type = file_type
        self._raw_name = raw_name
        self.size = size
        self.start_cluster = start_cluster
        self.created_at = created_at
        self.modified_at = modified_at

    @property
    def is_file(self) -> bool:
        return self._file_type == _TYPE_FILE

    @property
    def name(self) -> str:
        return self._raw_name.rstrip(b'\x00').decode('ascii').rstrip()

    def clusters_needed(self) -> int:
        return math.ceil(self.size / CLUSTER_SIZE) if self.size else 0

    def created_datetime(self) -> datetime | None:
        try:
            return datetime.strptime(self.created_at, _DATE_FMT)
        except ValueError:
            return None

    def modified_datetime(self) -> datetime | None:
        try:
            return datetime.strptime(self.modified_at, _DATE_FMT)
        except ValueError:
            return None

    def to_bytes(self) -> bytes:
        name_b = self._raw_name[:15].ljust(15, b'\x00')
        ctime_b = self.created_at[:14].encode('ascii').ljust(14, b'\x00')
        mtime_b = self.modified_at[:14].encode('ascii').ljust(14, b'\x00')
        return struct.pack(
            _ENTRY_FMT,
            self._file_type,
            name_b,
            self.size,
            self.start_cluster,
            ctime_b,
            mtime_b,
        )

    @classmethod
    def from_bytes(cls, raw: bytes, index: int) -> 'DirectoryEntry':
        ftype, fname, fsize, fcluster, fctime, fmtime = struct.unpack(
            _ENTRY_FMT, raw
        )
        return cls(
            index=index,
            file_type=ftype,
            raw_name=fname,
            size=fsize,
            start_cluster=fcluster,
            created_at=fctime.rstrip(b'\x00').decode('ascii'),
            modified_at=fmtime.rstrip(b'\x00').decode('ascii'),
        )

    @classmethod
    def new_file(
        cls,
        name: str,
        size: int,
        start_cluster: int,
        index: int = -1,
    ) -> 'DirectoryEntry':
        if len(name) > 15:
            raise DirectoryError(
                f"Nombre demasiado largo: '{name}' ({len(name)} > 15)"
            )
        now = datetime.now().strftime(_DATE_FMT)
        return cls(
            index=index,
            file_type=_TYPE_FILE,
            raw_name=name.encode('ascii').ljust(15, b'\x00'),
            size=size,
            start_cluster=start_cluster,
            created_at=now,
            modified_at=now,
        )

    @classmethod
    def tombstone(cls, index: int = -1) -> 'DirectoryEntry':
        return cls(
            index=index,
            file_type=_TYPE_FREE,
            raw_name=_EMPTY_NAME,
            size=0,
            start_cluster=0,
            created_at='00000000000000',
            modified_at='00000000000000',
        )

    def __repr__(self) -> str:
        if self.is_file:
            return (
                f"DirectoryEntry({self.index}: '{self.name}' "
                f"{self.size}B @C{self.start_cluster})"
            )
        return f"DirectoryEntry({self.index}: <libre>)"


class Directory:
    _DIR_START_CLUSTER = 1

    def __init__(
        self, disk: FiUnamFSDisk, superblock: Superblock
    ) -> None:
        self._disk = disk
        self._sb = superblock
        self._entries: list[DirectoryEntry] = []
        self._load()

    @property
    def max_entries(self) -> int:
        return (self._sb.dir_clusters * CLUSTER_SIZE) // ENTRY_SIZE

    def _dir_offset(self) -> int:
        return self._DIR_START_CLUSTER * CLUSTER_SIZE

    def _load(self) -> None:
        total_bytes = self._sb.dir_clusters * CLUSTER_SIZE
        raw = self._disk.read_bytes(self._dir_offset(), total_bytes)
        # Rebanamos el bloque crudo en trozos de ENTRY_SIZE y deserializamos cada uno;
        # i coincide con la ranura física de la entrada dentro del directorio en disco.
        self._entries = [
            DirectoryEntry.from_bytes(
                raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE], i
            )
            for i in range(self.max_entries)
        ]

    def _write_entry(self, index: int) -> None:
        offset = self._dir_offset() + index * ENTRY_SIZE
        self._disk.write_bytes(offset, self._entries[index].to_bytes())

    def list_files(self) -> list[DirectoryEntry]:
        return [e for e in self._entries if e.is_file]

    def find(self, name: str) -> DirectoryEntry | None:
        for entry in self._entries:
            if entry.is_file and entry.name == name:
                return entry
        return None

    def _find_empty_slot(self) -> int | None:
        for entry in self._entries:
            if not entry.is_file:
                return entry.index
        return None

    def used_clusters(self) -> set[int]:
        occupied: set[int] = set()
        for e in self._entries:
            if not e.is_file:
                continue
            for c in range(
                e.start_cluster, e.start_cluster + e.clusters_needed()
            ):
                occupied.add(c)
        return occupied

    def find_contiguous_clusters(self, n: int) -> int | None:
        """Primer bloque libre de n clusters consecutivos en la zona de datos."""
        if n == 0:
            return self._sb.data_start_cluster
        occupied = self.used_clusters()
        # Rastreamos la racha libre actual con (run_start, run_len).
        # Al topar con un cluster ocupado reiniciamos: run_start salta al siguiente
        # candidato y run_len vuelve a cero sin necesidad de retroceder.
        run_start = self._sb.data_start_cluster
        run_len = 0
        for c in range(
            self._sb.data_start_cluster, self._sb.total_clusters
        ):
            if c not in occupied:
                run_len += 1
                if run_len == n:
                    return run_start
            else:
                run_start = c + 1
                run_len = 0
        return None

    def add_entry(self, entry: DirectoryEntry) -> int:
        slot = self._find_empty_slot()
        if slot is None:
            raise DirectoryError(
                "Directorio lleno: no hay entradas disponibles"
            )
        entry.index = slot
        self._entries[slot] = entry
        self._write_entry(slot)
        return slot

    def delete_entry(self, name: str) -> DirectoryEntry:
        entry = self.find(name)
        if entry is None:
            raise DirectoryError(f"Archivo no encontrado: '{name}'")
        deleted = entry
        self._entries[entry.index] = DirectoryEntry.tombstone(entry.index)
        self._write_entry(entry.index)
        return deleted

    def update_entry(self, entry: DirectoryEntry) -> None:
        """Reescritura in-place de una entrada existente; usado por defrag."""
        self._entries[entry.index] = entry
        self._write_entry(entry.index)
