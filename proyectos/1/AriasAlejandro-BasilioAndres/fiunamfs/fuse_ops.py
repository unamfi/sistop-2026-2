import errno
import os
import stat
import tempfile
from typing import Any

from fuse import FUSE, FuseOSError, Operations

from .disk import CLUSTER_SIZE
from .exceptions import FilesystemError
from .filesystem import FiUnamFS


class FiUnamFSFuse(Operations):
    def __init__(self, fs: FiUnamFS) -> None:
        self._fs = fs
        self._buffers: dict[str, bytearray] = {}

    # --- metadata ---

    def getattr(self, path: str, fh: int | None = None) -> dict[str, Any]:
        if path == '/':
            return {'st_mode': stat.S_IFDIR | 0o755, 'st_nlink': 2}

        # Archivo aún en vuelo (create+write antes de release)
        if path in self._buffers:
            return {
                'st_mode': stat.S_IFREG | 0o644,
                'st_nlink': 1,
                'st_size': len(self._buffers[path]),
            }

        entry = self._fs.directory.find(path[1:])
        if entry is None:
            raise FuseOSError(errno.ENOENT)

        attrs: dict[str, Any] = {
            'st_mode': stat.S_IFREG | 0o644,
            'st_nlink': 1,
            'st_size': entry.size,
        }
        if (cdt := entry.created_datetime()) is not None:
            attrs['st_ctime'] = cdt.timestamp()
        if (mdt := entry.modified_datetime()) is not None:
            attrs['st_mtime'] = mdt.timestamp()
        return attrs

    def readdir(self, path: str, fh: int):
        yield '.'
        yield '..'
        for e in self._fs.directory.list_files():
            yield e.name

    # --- lectura ---

    def read(self, path: str, length: int, offset: int, fh: int) -> bytes:
        entry = self._fs.directory.find(path[1:])
        if entry is None:
            raise FuseOSError(errno.ENOENT)

        data = bytearray()
        remaining = entry.size
        for c in range(
            entry.start_cluster,
            entry.start_cluster + entry.clusters_needed(),
        ):
            block = self._fs.disk.read_cluster(c)
            data.extend(block[:remaining])
            remaining -= CLUSTER_SIZE

        return bytes(data)[offset:offset + length]

    # --- escritura con buffer en memoria ---

    def create(self, path: str, mode: int) -> int:
        if self._fs.directory.find(path[1:]) is not None:
            raise FuseOSError(errno.EEXIST)
        self._buffers[path] = bytearray()
        return 0

    def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
        buf = self._buffers.setdefault(path, bytearray())
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b'\x00' * (end - len(buf)))
        buf[offset:end] = data
        return len(data)

    def truncate(self, path: str, length: int, fh: int | None = None) -> None:
        buf = self._buffers.setdefault(path, bytearray())
        if length < len(buf):
            del buf[length:]
        else:
            buf.extend(b'\x00' * (length - len(buf)))

    def release(self, path: str, fh: int) -> int:
        if path not in self._buffers:
            return 0

        data = bytes(self._buffers.pop(path))

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmppath = tmp.name

        try:
            self._fs.cp_in(tmppath, path[1:])
        except FilesystemError as exc:
            raise FuseOSError(errno.ENOSPC) from exc
        finally:
            os.unlink(tmppath)

        return 0

    # --- borrado ---

    def unlink(self, path: str) -> None:
        try:
            self._fs.rm(path[1:])
        except FilesystemError:
            raise FuseOSError(errno.ENOENT)

    # --- montaje ---

    def mount(self, mountpoint: str, foreground: bool = True) -> None:
        FUSE(self, mountpoint, nothreads=True, foreground=foreground)
