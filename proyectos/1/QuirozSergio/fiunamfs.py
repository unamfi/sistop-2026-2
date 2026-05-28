"""
fiunamfs.py — Cliente multihilos para el sistema de archivos FiUnamFS.

Autor: Quiroz Salazar Sergio — Sistemas Operativos
Descripción:
    Implementa las operaciones de lectura/escritura sobre una imagen de disco
    que sigue la especificación FiUnamFS. Usa dos hilos concurrentes que se
    comunican su estado mediante un objeto de sincronización (threading.Lock +
    threading.Event), garantizando que las operaciones de lectura y escritura
    sobre la imagen no corrompan el directorio ni los datos.

Uso:
    python fiunamfs.py <imagen> <comando> [argumentos]

Comandos:
    list                        Lista el contenido del directorio
    copy-out <nombre> <destino> Copia un archivo del FS a tu PC
    copy-in  <origen> <nombre>  Copia un archivo de tu PC al FS
    delete   <nombre>           Elimina un archivo del FS
"""

import struct
import threading
import os
import sys
import time
from datetime import datetime


#  Constantes de la especificación FiUnamFS
SECTOR_SIZE       = 512          # bytes por sector
SECTORS_PER_CLUSTER = 4          # sectores por cluster
CLUSTER_SIZE      = SECTOR_SIZE * SECTORS_PER_CLUSTER  # 2048 bytes

# Superbloque (cluster 0)
SB_MAGIC_OFF      = 0            # 5 bytes  → \x00\x00\x00\x00\x00
SB_NAME_OFF       = 5            # 9 bytes  → "FiUnamFS"
SB_VERSION_OFF    = 14           # 5 bytes  → "24-2" o "26-2"
SB_LABEL_OFF      = 20           # 16 bytes → etiqueta del volumen
SB_CLUSTER_SZ_OFF = 40           # 4 bytes  → tamaño cluster (little-endian u32)
SB_DIR_CLS_OFF    = 50           # 4 bytes  → clusters de directorio
SB_TOTAL_CLS_OFF  = 60           # 4 bytes  → clusters totales en disco

FS_NAME           = b"FiUnamFS"
VALID_VERSIONS    = {b"24-2", b"26-2"}  # admitimos ambas por seguridad

# Directorio (clusters 1..8 por defecto)
DIR_START_CLUSTER = 1
ENTRY_SIZE        = 64           # bytes por entrada de directorio

# Bytes de tipo de entrada
TYPE_FILE         = 0x2d         # '-'
TYPE_EMPTY        = 0x2f         # '/'

# Offsets dentro de cada entrada (64 bytes)
DE_TYPE_OFF       = 0            # 1 byte
DE_NAME_OFF       = 1            # 15 bytes
DE_SIZE_OFF       = 16           # 4 bytes (u32 LE)  [16-20)
DE_CLUSTER_OFF    = 20           # 4 bytes (u32 LE)  [20-24)
DE_CTIME_OFF      = 30           # 15 bytes AAAAMMDDHHMMSS
DE_MTIME_OFF      = 50           # 15 bytes AAAAMMDDHHMMSS

DATE_FMT          = "%Y%m%d%H%M%S"


#  Estado compartido entre hilos
class SharedState:
    """
    Contiene el estado compartido entre el hilo de control (UI) y el hilo
    de trabajo (I/O). El Lock protege el acceso a `resultado` y `error`.
    El Event `listo` se usa para que el hilo de control espere sin busy-wait
    a que el hilo de trabajo termine su operación.
    """
    def __init__(self):
        self.lock    = threading.Lock()
        self.listo   = threading.Event()
        self.resultado = None   # objeto devuelto por la operación
        self.error     = None   # excepción capturada, si hubo


#  Clase principal del sistema de archivos
class FiUnamFS:
    """
    Abstracción sobre una imagen de disco FiUnamFS.
    Todas las operaciones de bajo nivel (leer/escribir sectores, parsear
    el directorio, etc.) viven aquí. Las llamadas públicas son thread-safe
    gracias al _fs_lock interno.
    """

    def __init__(self, path: str):
        self.path    = path
        self._fs_lock = threading.Lock()  # protege el archivo de imagen
        self._validate()

    # Helpers de I/O

    def _read_cluster(self, n: int) -> bytes:
        """Lee y devuelve los bytes del cluster n."""
        with open(self.path, "rb") as f:
            f.seek(n * CLUSTER_SIZE)
            return f.read(CLUSTER_SIZE)

    def _write_cluster(self, n: int, data: bytes):
        """Escribe `data` en el cluster n (se rellena con \x00 si es corto)."""
        assert len(data) <= CLUSTER_SIZE
        data = data.ljust(CLUSTER_SIZE, b"\x00")
        with open(self.path, "r+b") as f:
            f.seek(n * CLUSTER_SIZE)
            f.write(data)

    def _read_bytes(self, offset: int, length: int) -> bytes:
        """Lee `length` bytes desde `offset` absoluto en el disco."""
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(length)

    def _write_bytes(self, offset: int, data: bytes):
        """Escribe `data` en `offset` absoluto en el disco."""
        with open(self.path, "r+b") as f:
            f.seek(offset)
            f.write(data)

    # Superbloque

    def _validate(self):
        """Lee el superbloque y verifica nombre y versión."""
        sb = self._read_cluster(0)

        name    = sb[SB_NAME_OFF: SB_NAME_OFF + 8].rstrip(b"\x00")
        version = sb[SB_VERSION_OFF: SB_VERSION_OFF + 4].rstrip(b"\x00")

        if name != FS_NAME:
            raise ValueError(f"No es un FiUnamFS válido (nombre='{name}')")
        if version not in VALID_VERSIONS:
            raise ValueError(f"Versión no soportada: '{version.decode()}'. "
                             f"Se esperaba: {[v.decode() for v in VALID_VERSIONS]}")

        self.cluster_size  = struct.unpack_from("<I", sb, SB_CLUSTER_SZ_OFF)[0]
        self.dir_clusters  = struct.unpack_from("<I", sb, SB_DIR_CLS_OFF)[0]
        self.total_clusters = struct.unpack_from("<I", sb, SB_TOTAL_CLS_OFF)[0]
        self.label         = sb[SB_LABEL_OFF: SB_LABEL_OFF + 16].decode("ascii", errors="replace").rstrip("\x00 ")
        self.version       = version.decode("ascii")

    # Directorio

    def _dir_raw(self) -> bytes:
        """Devuelve los bytes crudos de toda la zona de directorio."""
        chunks = []
        for c in range(DIR_START_CLUSTER, DIR_START_CLUSTER + self.dir_clusters):
            chunks.append(self._read_cluster(c))
        return b"".join(chunks)

    def _entries(self):
        """
        Generador que produce (índice, dict) por cada entrada del directorio,
        incluyendo las vacías.
        """
        raw = self._dir_raw()
        n   = len(raw) // ENTRY_SIZE
        for i in range(n):
            e = raw[i * ENTRY_SIZE: (i + 1) * ENTRY_SIZE]
            tipo = e[DE_TYPE_OFF]
            yield i, {
                "tipo":    tipo,
                "nombre":  e[DE_NAME_OFF: DE_NAME_OFF + 15].decode("ascii", errors="replace").rstrip("\x00 "),
                "size":    struct.unpack_from("<I", e, DE_SIZE_OFF)[0],
                "cluster": struct.unpack_from("<I", e, DE_CLUSTER_OFF)[0],
                "ctime":   e[DE_CTIME_OFF: DE_CTIME_OFF + 15].decode("ascii", errors="replace").rstrip("\x00"),
                "mtime":   e[DE_MTIME_OFF: DE_MTIME_OFF + 15].decode("ascii", errors="replace").rstrip("\x00"),
            }

    def _find_file(self, nombre: str):
        """Devuelve (índice, entrada) de un archivo por nombre, o (None, None)."""
        for i, e in self._entries():
            if e["tipo"] == TYPE_FILE and e["nombre"] == nombre:
                return i, e
        return None, None

    def _find_empty_entry(self):
        """Devuelve el índice de la primera entrada libre del directorio."""
        for i, e in self._entries():
            if e["tipo"] == TYPE_EMPTY:
                return i
        return None

    def _write_entry(self, idx: int, entry_bytes: bytes):
        """Escribe una entrada de 64 bytes en la posición `idx` del directorio."""
        # El directorio empieza en el cluster DIR_START_CLUSTER
        dir_offset = DIR_START_CLUSTER * CLUSTER_SIZE + idx * ENTRY_SIZE
        self._write_bytes(dir_offset, entry_bytes[:ENTRY_SIZE])

    @staticmethod
    def _pack_entry(tipo: int, nombre: str, size: int, cluster: int,
                    ctime: str, mtime: str) -> bytes:
        """Empaqueta los campos de una entrada de directorio en 64 bytes."""
        e = bytearray(ENTRY_SIZE)
        e[DE_TYPE_OFF] = tipo

        # Nombre: 15 bytes, rellenado con espacios para mantener alineación
        nombre_b = nombre.encode("ascii")[:15].ljust(15, b" ")
        e[DE_NAME_OFF: DE_NAME_OFF + 15] = nombre_b

        struct.pack_into("<I", e, DE_SIZE_OFF,    size)
        struct.pack_into("<I", e, DE_CLUSTER_OFF, cluster)

        ctime_b = ctime.encode("ascii")[:15].ljust(15, b"\x00")
        mtime_b = mtime.encode("ascii")[:15].ljust(15, b"\x00")
        e[DE_CTIME_OFF: DE_CTIME_OFF + 15] = ctime_b
        e[DE_MTIME_OFF: DE_MTIME_OFF + 15] = mtime_b
        return bytes(e)

    # Espacio libre en datos

    def _clusters_needed(self, size: int) -> int:
        """Calcula cuántos clusters se necesitan para `size` bytes."""
        return (size + CLUSTER_SIZE - 1) // CLUSTER_SIZE

    def _used_regions(self):
        """
        Devuelve lista de (cluster_inicio, cluster_fin_exclusive) de todos
        los archivos existentes, más la zona reservada (superbloque+directorio).
        """
        regions = [(0, DIR_START_CLUSTER + self.dir_clusters)]  # zona reservada
        for _, e in self._entries():
            if e["tipo"] == TYPE_FILE and e["size"] > 0:
                n = self._clusters_needed(e["size"])
                regions.append((e["cluster"], e["cluster"] + n))
        return sorted(regions)

    def _find_free_space(self, needed: int) -> int:
        """
        Busca `needed` clusters contiguos libres. Devuelve el cluster inicial
        o lanza IOError si no hay espacio.
        """
        regions = self._used_regions()
        prev_end = 0
        for start, end in regions:
            gap = start - prev_end
            if gap >= needed:
                return prev_end
            prev_end = max(prev_end, end)
        # Espacio después de la última región
        if self.total_clusters - prev_end >= needed:
            return prev_end
        raise IOError("No hay espacio suficiente en el disco FiUnamFS")

    # API pública (thread-safe)

    def list_files(self) -> list[dict]:
        """Devuelve la lista de archivos en el directorio."""
        with self._fs_lock:
            files = []
            for _, e in self._entries():
                if e["tipo"] == TYPE_FILE:
                    files.append(e)
            return files

    def copy_out(self, nombre: str, dest_path: str):
        """Copia un archivo del FiUnamFS a `dest_path` en el sistema local."""
        with self._fs_lock:
            idx, entry = self._find_file(nombre)
            if idx is None:
                raise FileNotFoundError(f"'{nombre}' no existe en FiUnamFS")

            size    = entry["size"]
            cluster = entry["cluster"]
            offset  = cluster * CLUSTER_SIZE

            data = self._read_bytes(offset, size)

        with open(dest_path, "wb") as f:
            f.write(data)

    def copy_in(self, src_path: str, nombre: str):
        """Copia `src_path` del sistema local hacia FiUnamFS con el nombre dado."""
        if not os.path.isfile(src_path):
            raise FileNotFoundError(f"Archivo local '{src_path}' no encontrado")

        with open(src_path, "rb") as f:
            data = f.read()

        size = len(data)
        if size == 0:
            raise ValueError("No se pueden copiar archivos vacíos")

        with self._fs_lock:
            # Verificar que no exista ya
            idx_exist, _ = self._find_file(nombre)
            if idx_exist is not None:
                raise FileExistsError(f"'{nombre}' ya existe en FiUnamFS. "
                                      "Elimínalo primero.")

            needed = self._clusters_needed(size)
            cluster_ini = self._find_free_space(needed)

            now = datetime.now().strftime(DATE_FMT)
            entry_bytes = self._pack_entry(TYPE_FILE, nombre, size,
                                           cluster_ini, now, now)

            idx_free = self._find_empty_entry()
            if idx_free is None:
                raise IOError("Directorio lleno, no hay entradas disponibles")

            # Escribir datos primero
            self._write_bytes(cluster_ini * CLUSTER_SIZE, data)
            # Luego registrar en directorio
            self._write_entry(idx_free, entry_bytes)

    def delete(self, nombre: str):
        """Marca la entrada del archivo como vacía ('/') y borra sus datos."""
        with self._fs_lock:
            idx, entry = self._find_file(nombre)
            if idx is None:
                raise FileNotFoundError(f"'{nombre}' no existe en FiUnamFS")

            size    = entry["size"]
            cluster = entry["cluster"]
            needed  = self._clusters_needed(size)

            # Borrar datos (rellenar con ceros)
            zeros = b"\x00" * (needed * CLUSTER_SIZE)
            self._write_bytes(cluster * CLUSTER_SIZE, zeros)

            # Marcar entrada como vacía
            empty_entry = bytearray(ENTRY_SIZE)
            empty_entry[DE_TYPE_OFF] = TYPE_EMPTY
            self._write_entry(idx, bytes(empty_entry))


#  Hilo de trabajo (I/O worker)
def worker_thread(fs: FiUnamFS, operation, args: tuple, state: SharedState):
    """
    Hilo secundario que ejecuta `operation(fs, *args)` y deposita el
    resultado (o la excepción) en `state`, luego señala `state.listo`.

    Sincronización:
      - state.lock  → escritura exclusiva en state.resultado / state.error
      - state.listo → señal para que el hilo principal deje de esperar
    """
    try:
        result = operation(fs, *args)
        with state.lock:
            state.resultado = result
            state.error     = None
    except Exception as exc:
        with state.lock:
            state.resultado = None
            state.error     = exc
    finally:
        state.listo.set()   # desbloquea al hilo de control


def run_operation(fs: FiUnamFS, operation, args: tuple = ()):
    """
    Lanza la operación en un hilo separado, espera a que termine
    (bloqueando con Event.wait()) y devuelve el resultado o relanza
    la excepción capturada.
    """
    state = SharedState()
    t = threading.Thread(
        target=worker_thread,
        args=(fs, operation, args, state),
        daemon=True,
        name="fiunamfs-worker"
    )
    t.start()

    # Hilo principal espera sin busy-wait gracias al Event
    state.listo.wait()
    t.join()

    with state.lock:
        if state.error is not None:
            raise state.error
        return state.resultado


#  Operaciones como funciones independientes
#  (para pasarlas al hilo de trabajo)
def op_list(fs: FiUnamFS) -> list[dict]:
    return fs.list_files()

def op_copy_out(fs: FiUnamFS, nombre: str, dest: str):
    fs.copy_out(nombre, dest)

def op_copy_in(fs: FiUnamFS, src: str, nombre: str):
    fs.copy_in(src, nombre)

def op_delete(fs: FiUnamFS, nombre: str):
    fs.delete(nombre)


#  Interfaz de línea de comandos
def fmt_date(raw: str) -> str:
    """Formatea AAAAMMDDHHMMSS → AAAA-MM-DD HH:MM:SS (para mostrar)."""
    try:
        dt = datetime.strptime(raw, DATE_FMT)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw

def fmt_size(n: int) -> str:
    """Tamaño legible."""
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} GB"


def cmd_list(fs: FiUnamFS, _args):
    files = run_operation(fs, op_list)
    if not files:
        print("(Directorio vacío)")
        return

    header = f"{'Nombre':<16} {'Tamaño':>10}  {'Cluster':>7}  {'Creado':<19}  {'Modificado':<19}"
    print(header)
    print("─" * len(header))
    for e in files:
        print(f"{e['nombre']:<16} {fmt_size(e['size']):>10}  {e['cluster']:>7}  "
              f"{fmt_date(e['ctime']):<19}  {fmt_date(e['mtime']):<19}")
    print(f"\n{len(files)} archivo(s)")


def cmd_copy_out(fs: FiUnamFS, args):
    if len(args) < 2:
        print("Uso: copy-out <nombre_en_fs> <destino_local>")
        sys.exit(1)
    nombre, dest = args[0], args[1]
    print(f"Copiando '{nombre}' → '{dest}' ...")
    run_operation(fs, op_copy_out, (nombre, dest))
    size = os.path.getsize(dest)
    print(f"Listo. {fmt_size(size)} escritos en '{dest}'")


def cmd_copy_in(fs: FiUnamFS, args):
    if len(args) < 2:
        print("Uso: copy-in <archivo_local> <nombre_en_fs>")
        sys.exit(1)
    src, nombre = args[0], args[1]
    print(f"Copiando '{src}' → FiUnamFS:'{nombre}' ...")
    run_operation(fs, op_copy_in, (src, nombre))
    print(f"Listo. '{nombre}' agregado al sistema de archivos.")


def cmd_delete(fs: FiUnamFS, args):
    if len(args) < 1:
        print("Uso: delete <nombre_en_fs>")
        sys.exit(1)
    nombre = args[0]
    print(f"Eliminando '{nombre}' ...")
    run_operation(fs, op_delete, (nombre,))
    print(f"Listo. '{nombre}' eliminado del sistema de archivos.")


COMMANDS = {
    "list":      cmd_list,
    "copy-out":  cmd_copy_out,
    "copy-in":   cmd_copy_in,
    "delete":    cmd_delete,
}

HELP = """
Uso:
  python fiunamfs.py <imagen.img> <comando> [argumentos]

Comandos:
  list                              Lista los archivos del directorio
  copy-out <nombre> <destino>       Copia un archivo del FS a tu PC
  copy-in  <origen> <nombre_en_fs>  Copia un archivo de tu PC al FS
  delete   <nombre>                 Elimina un archivo del FS

Ejemplos:
  python fiunamfs.py fiunamfs.img list
  python fiunamfs.py fiunamfs.img copy-out README.org ./README.org
  python fiunamfs.py fiunamfs.img copy-in   ./foto.jpg foto.jpg
  python fiunamfs.py fiunamfs.img delete    foto.jpg
"""


def main():
    if len(sys.argv) < 3:
        print(HELP)
        sys.exit(0)

    img_path = sys.argv[1]
    command  = sys.argv[2]
    rest     = sys.argv[3:]

    if command not in COMMANDS:
        print(f"Comando desconocido: '{command}'\n{HELP}")
        sys.exit(1)

    try:
        fs = FiUnamFS(img_path)
    except (ValueError, IOError) as e:
        print(f"Error al abrir la imagen: {e}")
        sys.exit(1)

    try:
        COMMANDS[command](fs, rest)
    except (FileNotFoundError, FileExistsError, IOError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
# Fin del módulo fiunamfs — Quiroz Salazar Sergio, 2026
# Sincronización: threading.Lock + threading.Event entre hilo de control y worker
