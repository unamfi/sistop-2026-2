#!/usr/bin/env python3
"""
FiUnamFS — Micro-sistema de archivos sobre imagen de 1440 KB.

Soporta listado, extracción, inserción y borrado lógico de archivos
sobre el sistema de archivos FiUnamFS (versión 26-2). Cada operación
del usuario corre en un hilo independiente; un Lock global serializa
los accesos a la imagen para evitar condiciones de carrera sobre el
directorio o el área de datos.
"""

import argparse
import math
import os
import struct
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Layout físico del disco
# ---------------------------------------------------------------------------
TAMANIO_SECTOR = 512
SECTORES_POR_CLUSTER = 4
TAMANIO_CLUSTER = TAMANIO_SECTOR * SECTORES_POR_CLUSTER  # 2048 B
TAMANIO_IMAGEN = 1440 * 1024
TOTAL_CLUSTERS = TAMANIO_IMAGEN // TAMANIO_CLUSTER


# ---------------------------------------------------------------------------
# Superbloque (clúster 0)
# ---------------------------------------------------------------------------
OFFSET_NOMBRE_FS = 5
LONGITUD_NOMBRE_FS = 8
NOMBRE_FS_ESPERADO = b'FiUnamFS'

OFFSET_VERSION_FS = 14
LONGITUD_VERSION_FS = 4
VERSION_FS_ESPERADA = b'26-2'


# ---------------------------------------------------------------------------
# Directorio plano: clústeres 1 a 8, entradas de 64 bytes
# ---------------------------------------------------------------------------
CLUSTER_INICIO_DIRECTORIO = 1
NUM_CLUSTERS_DIRECTORIO = 8
TAMANIO_ENTRADA = 64

# Layout de una entrada de 64 bytes (verificado contra la imagen de muestra):
#   byte  0       : tipo ('-' archivo, '/' entrada libre)
#   bytes 1-14    : nombre (14 chars ASCII, rellenado con espacios o NUL)
#   bytes 16-19   : tamaño en bytes (uint32 LE)
#   bytes 20-23   : clúster inicial (uint32 LE)
#   bytes 30-43   : fecha de creación      'AAAAMMDDHHmmss'
#   bytes 50-63   : fecha de modificación  'AAAAMMDDHHmmss'
OFFSET_TIPO = 0
OFFSET_NOMBRE = 1
LONGITUD_NOMBRE = 14
OFFSET_TAMANIO = 16
OFFSET_CLUSTER_INICIAL = 20
OFFSET_FECHA_CREACION = 30
OFFSET_FECHA_MODIFICACION = 50
LONGITUD_FECHA = 14

TIPO_ARCHIVO = b'-'          # 0x2d
TIPO_ENTRADA_LIBRE = b'/'    # 0x2f
RELLENO_NOMBRE_LIBRE = 0x23  # '#'

CLUSTER_INICIO_DATOS = CLUSTER_INICIO_DIRECTORIO + NUM_CLUSTERS_DIRECTORIO


# ---------------------------------------------------------------------------
# Exclusión mutua sobre la imagen
# ---------------------------------------------------------------------------
# Un único Lock global serializa todo acceso a la imagen. Cada operación
# que toca el directorio o el área de datos lo hace dentro de un bloque
# `with cerrojo:`, garantizando que la decisión de dónde escribir y la
# escritura misma sean atómicas frente a otros hilos.
cerrojo = threading.Lock()


@dataclass
class EntradaDirectorio:
    nombre: str
    tamanio: int
    cluster_inicial: int
    fecha_creacion: Optional[datetime]
    fecha_modificacion: Optional[datetime]
    offset_en_disco: int  # byte absoluto del inicio de la entrada


# ---------------------------------------------------------------------------
# Superbloque
# ---------------------------------------------------------------------------
def validar_imagen(ruta: str) -> None:
    """Comprueba que la imagen tenga el tamaño, firma y versión correctos."""
    if not os.path.isfile(ruta):
        raise FileNotFoundError(f'No existe la imagen «{ruta}».')
    if os.path.getsize(ruta) != TAMANIO_IMAGEN:
        raise ValueError(
            f'La imagen mide {os.path.getsize(ruta)} bytes; se esperaban '
            f'{TAMANIO_IMAGEN}. ¿Está truncada?'
        )

    with open(ruta, 'rb') as f:
        superbloque = f.read(TAMANIO_CLUSTER)

    (firma,) = struct.unpack_from(
        f'{LONGITUD_NOMBRE_FS}s', superbloque, OFFSET_NOMBRE_FS
    )
    if firma != NOMBRE_FS_ESPERADO:
        raise ValueError(
            f'Firma inválida: se esperaba «{NOMBRE_FS_ESPERADO.decode()}», '
            f'se encontró «{firma.decode(errors="replace")}».'
        )

    (version,) = struct.unpack_from(
        f'{LONGITUD_VERSION_FS}s', superbloque, OFFSET_VERSION_FS
    )
    if version != VERSION_FS_ESPERADA:
        raise ValueError(
            f'Versión incompatible: se esperaba «{VERSION_FS_ESPERADA.decode()}», '
            f'se encontró «{version.decode(errors="replace")}».'
        )


# ---------------------------------------------------------------------------
# Lectura del directorio
# ---------------------------------------------------------------------------
def _decodificar_fecha(crudo: bytes) -> Optional[datetime]:
    try:
        return datetime.strptime(crudo.decode('ascii'), '%Y%m%d%H%M%S')
    except (ValueError, UnicodeDecodeError):
        return None


def _es_entrada_libre(bloque: bytes) -> bool:
    if bloque[OFFSET_TIPO:OFFSET_TIPO + 1] == TIPO_ENTRADA_LIBRE:
        return True
    nombre = bloque[OFFSET_NOMBRE:OFFSET_NOMBRE + LONGITUD_NOMBRE]
    return all(b == RELLENO_NOMBRE_LIBRE for b in nombre)


def _parsear_entrada(bloque: bytes, offset_en_disco: int) -> EntradaDirectorio:
    nombre_crudo = bloque[OFFSET_NOMBRE:OFFSET_NOMBRE + LONGITUD_NOMBRE]
    nombre = nombre_crudo.decode('ascii', errors='replace').rstrip(' \x00')

    (tamanio,) = struct.unpack_from('<I', bloque, OFFSET_TAMANIO)
    (cluster,) = struct.unpack_from('<I', bloque, OFFSET_CLUSTER_INICIAL)

    creacion = _decodificar_fecha(
        bloque[OFFSET_FECHA_CREACION:OFFSET_FECHA_CREACION + LONGITUD_FECHA]
    )
    modificacion = _decodificar_fecha(
        bloque[OFFSET_FECHA_MODIFICACION:OFFSET_FECHA_MODIFICACION + LONGITUD_FECHA]
    )

    return EntradaDirectorio(
        nombre=nombre,
        tamanio=tamanio,
        cluster_inicial=cluster,
        fecha_creacion=creacion,
        fecha_modificacion=modificacion,
        offset_en_disco=offset_en_disco,
    )


def _leer_directorio_crudo(ruta: str) -> bytes:
    with open(ruta, 'rb') as f:
        f.seek(CLUSTER_INICIO_DIRECTORIO * TAMANIO_CLUSTER)
        return f.read(NUM_CLUSTERS_DIRECTORIO * TAMANIO_CLUSTER)


def leer_directorio(ruta: str) -> list:
    """Devuelve las entradas activas (no libres) del directorio."""
    crudo = _leer_directorio_crudo(ruta)
    base = CLUSTER_INICIO_DIRECTORIO * TAMANIO_CLUSTER
    entradas = []
    for i in range(len(crudo) // TAMANIO_ENTRADA):
        bloque = crudo[i * TAMANIO_ENTRADA:(i + 1) * TAMANIO_ENTRADA]
        if _es_entrada_libre(bloque):
            continue
        entradas.append(_parsear_entrada(bloque, base + i * TAMANIO_ENTRADA))
    return entradas


def _buscar_entrada(entradas: list, nombre: str) -> EntradaDirectorio:
    for e in entradas:
        if e.nombre == nombre:
            return e
    raise ValueError(f'No existe «{nombre}» en FiUnamFS.')


# ---------------------------------------------------------------------------
# Asignación de espacio
# ---------------------------------------------------------------------------
def _clusters_necesarios(tamanio: int) -> int:
    return math.ceil(tamanio / TAMANIO_CLUSTER)


def _clusters_ocupados(entradas: list) -> set:
    ocup = set()
    for e in entradas:
        for c in range(e.cluster_inicial,
                       e.cluster_inicial + _clusters_necesarios(e.tamanio)):
            ocup.add(c)
    return ocup


def _primer_hueco_contiguo(entradas: list, clusters: int) -> int:
    """First-fit sobre el área de datos."""
    ocup = _clusters_ocupados(entradas)
    inicio_candidato = CLUSTER_INICIO_DATOS
    libres_consecutivos = 0
    for c in range(CLUSTER_INICIO_DATOS, TOTAL_CLUSTERS):
        if c in ocup:
            inicio_candidato = c + 1
            libres_consecutivos = 0
        else:
            libres_consecutivos += 1
            if libres_consecutivos >= clusters:
                return inicio_candidato
    raise ValueError(
        f'No hay {clusters} clúster(es) contiguos libres en el área de datos.'
    )


def _offset_primera_entrada_libre(ruta: str) -> int:
    crudo = _leer_directorio_crudo(ruta)
    base = CLUSTER_INICIO_DIRECTORIO * TAMANIO_CLUSTER
    for i in range(len(crudo) // TAMANIO_ENTRADA):
        bloque = crudo[i * TAMANIO_ENTRADA:(i + 1) * TAMANIO_ENTRADA]
        if _es_entrada_libre(bloque):
            return base + i * TAMANIO_ENTRADA
    raise ValueError('El directorio está lleno; no hay entradas libres.')


# ---------------------------------------------------------------------------
# Operaciones del usuario (toda la I/O queda dentro de `cerrojo`)
# ---------------------------------------------------------------------------
def listar(ruta: str) -> None:
    with cerrojo:
        entradas = leer_directorio(ruta)

    if not entradas:
        print('(El directorio está vacío.)')
        return

    print(f'{"Nombre":<16} {"Tamaño":>10} {"Clúster":>8}  '
          f'{"Creación":<19}  {"Modificación":<19}')
    print('-' * 80)
    for e in entradas:
        crea = (e.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')
                if e.fecha_creacion else '—')
        modif = (e.fecha_modificacion.strftime('%Y-%m-%d %H:%M:%S')
                 if e.fecha_modificacion else '—')
        print(f'{e.nombre:<16} {e.tamanio:>10,} {e.cluster_inicial:>8}  '
              f'{crea:<19}  {modif:<19}')
    print('-' * 80)
    print(f'Total: {len(entradas)} archivo(s)')


def extraer(ruta: str, nombre: str, destino: str) -> None:
    with cerrojo:
        entradas = leer_directorio(ruta)
        entrada = _buscar_entrada(entradas, nombre)
        with open(ruta, 'rb') as imagen:
            imagen.seek(entrada.cluster_inicial * TAMANIO_CLUSTER)
            contenido = imagen.read(entrada.tamanio)

    # Si el destino es un directorio existente, conservar el nombre
    # original dentro de él (comportamiento tipo `cp`).
    if os.path.isdir(destino):
        destino = os.path.join(destino, nombre)

    with open(destino, 'wb') as salida:
        salida.write(contenido)

    print(f'Extraído «{nombre}» → «{destino}» ({entrada.tamanio:,} bytes).')


def _escribir_en_fs(ruta: str, nombre: str, contenido: bytes) -> tuple:
    """Escribe `contenido` como un archivo nuevo dentro de la imagen.

    Devuelve `(cluster_inicial, n_clusters)`. Adquiere el cerrojo
    internamente, así que sirve tanto para `insertar` (que lee de un
    archivo local) como para el módulo FUSE (que recibe los bytes
    desde un buffer en memoria).
    """
    tamanio = len(contenido)
    if tamanio == 0:
        raise ValueError('No se admite insertar un archivo vacío.')
    if len(nombre) > LONGITUD_NOMBRE:
        raise ValueError(
            f'El nombre «{nombre}» excede {LONGITUD_NOMBRE} caracteres.'
        )
    if not all(ord(c) < 128 for c in nombre):
        raise ValueError('El nombre contiene caracteres fuera de ASCII de 7 bits.')

    with cerrojo:
        entradas = leer_directorio(ruta)
        if any(e.nombre == nombre for e in entradas):
            raise ValueError(f'Ya existe «{nombre}» dentro de FiUnamFS.')

        n_clusters = _clusters_necesarios(tamanio)
        cluster_inicial = _primer_hueco_contiguo(entradas, n_clusters)
        offset_entrada = _offset_primera_entrada_libre(ruta)

        sello = datetime.now().strftime('%Y%m%d%H%M%S').encode('ascii')

        with open(ruta, 'r+b') as imagen:
            imagen.seek(cluster_inicial * TAMANIO_CLUSTER)
            imagen.write(contenido)

            # Rellenar el último clúster con ceros: evita exponer
            # residuos de un archivo previamente borrado en el mismo lugar.
            residuo = tamanio % TAMANIO_CLUSTER
            if residuo:
                imagen.write(b'\x00' * (TAMANIO_CLUSTER - residuo))

            registro = bytearray(TAMANIO_ENTRADA)
            registro[OFFSET_TIPO:OFFSET_TIPO + 1] = TIPO_ARCHIVO
            nombre_bytes = nombre.encode('ascii').ljust(LONGITUD_NOMBRE, b' ')
            registro[OFFSET_NOMBRE:OFFSET_NOMBRE + LONGITUD_NOMBRE] = nombre_bytes
            struct.pack_into('<I', registro, OFFSET_TAMANIO, tamanio)
            struct.pack_into('<I', registro, OFFSET_CLUSTER_INICIAL, cluster_inicial)
            registro[OFFSET_FECHA_CREACION:OFFSET_FECHA_CREACION + LONGITUD_FECHA] = sello
            registro[OFFSET_FECHA_MODIFICACION:OFFSET_FECHA_MODIFICACION + LONGITUD_FECHA] = sello

            imagen.seek(offset_entrada)
            imagen.write(registro)

    return cluster_inicial, n_clusters


def insertar(ruta: str, ruta_local: str) -> None:
    if not os.path.isfile(ruta_local):
        raise FileNotFoundError(f'No existe el archivo local «{ruta_local}».')

    nombre = os.path.basename(ruta_local)
    with open(ruta_local, 'rb') as f:
        contenido = f.read()

    cluster_inicial, n_clusters = _escribir_en_fs(ruta, nombre, contenido)
    print(f'Insertado «{nombre}» en clúster {cluster_inicial} '
          f'({len(contenido):,} bytes, {n_clusters} clúster(es)).')


def eliminar(ruta: str, nombre: str) -> None:
    """Borrado lógico: invalida la entrada sin tocar el área de datos."""
    with cerrojo:
        entradas = leer_directorio(ruta)
        entrada = _buscar_entrada(entradas, nombre)
        nombre_invalido = bytes([RELLENO_NOMBRE_LIBRE] * LONGITUD_NOMBRE)
        with open(ruta, 'r+b') as imagen:
            imagen.seek(entrada.offset_en_disco + OFFSET_TIPO)
            imagen.write(TIPO_ENTRADA_LIBRE)
            imagen.seek(entrada.offset_en_disco + OFFSET_NOMBRE)
            imagen.write(nombre_invalido)
    print(f'Eliminado «{nombre}».')


# ---------------------------------------------------------------------------
# Modo FUSE: montaje de la imagen como un directorio del sistema
# ---------------------------------------------------------------------------
# El módulo FUSE actúa como una segunda interfaz: en lugar de invocar
# los subcomandos del CLI, el usuario monta el FiUnamFS bajo cualquier
# directorio y opera con `ls`, `cp`, `cat` o `rm` como si fuera un
# directorio normal. Cada llamada del sistema se traduce internamente
# a las mismas funciones (`leer_directorio`, `_escribir_en_fs`,
# `eliminar`) que el CLI, así que el `cerrojo` sigue cuidando la
# imagen aunque varios procesos lean o escriban a la vez.
def _montar_fuse(ruta_imagen: str, punto_montaje: str) -> None:
    try:
        from fuse import FUSE, Operations, FuseOSError
    except (ImportError, OSError) as err:
        raise RuntimeError(
            'El modo «mount» requiere fusepy y libfuse instalados. '
            'En Debian/Ubuntu: sudo apt-get install fuse && pip install fusepy. '
            f'Detalle: {err}'
        )

    import errno
    import stat
    import time

    class FiUnamFS(Operations):
        """Adaptador entre la API de fusepy y nuestras funciones del FS."""

        def __init__(self, ruta_imagen: str):
            self.ruta = ruta_imagen
            # Buffers para archivos en curso de escritura. La inserción
            # real (escribir clústeres + entrada) se hace en `release`,
            # cuando ya conocemos el tamaño total del archivo.
            self._buffers: dict = {}
            self._cerrojo_buffers = threading.Lock()
            self._t_montaje = time.time()

        def _entrada_por_nombre(self, nombre: str):
            for e in leer_directorio(self.ruta):
                if e.nombre == nombre:
                    return e
            return None

        # -------- Lectura --------

        def getattr(self, path, fh=None):
            if path == '/':
                return {
                    'st_mode': stat.S_IFDIR | 0o755, 'st_nlink': 2,
                    'st_ctime': self._t_montaje,
                    'st_mtime': self._t_montaje,
                    'st_atime': self._t_montaje,
                }
            nombre = path.lstrip('/')
            with cerrojo:
                entrada = self._entrada_por_nombre(nombre)
            if entrada is not None:
                ct = (entrada.fecha_creacion.timestamp()
                      if entrada.fecha_creacion else self._t_montaje)
                mt = (entrada.fecha_modificacion.timestamp()
                      if entrada.fecha_modificacion else self._t_montaje)
                return {
                    'st_mode': stat.S_IFREG | 0o644, 'st_nlink': 1,
                    'st_size': entrada.tamanio,
                    'st_ctime': ct, 'st_mtime': mt, 'st_atime': mt,
                }
            with self._cerrojo_buffers:
                if path in self._buffers:
                    return {
                        'st_mode': stat.S_IFREG | 0o644, 'st_nlink': 1,
                        'st_size': len(self._buffers[path]),
                        'st_ctime': time.time(),
                        'st_mtime': time.time(),
                        'st_atime': time.time(),
                    }
            raise FuseOSError(errno.ENOENT)

        def readdir(self, path, fh):
            with cerrojo:
                entradas = leer_directorio(self.ruta)
            return ['.', '..'] + [e.nombre for e in entradas]

        def open(self, path, flags):
            nombre = path.lstrip('/')
            with cerrojo:
                existe = self._entrada_por_nombre(nombre) is not None
            with self._cerrojo_buffers:
                en_buffer = path in self._buffers
            if not existe and not en_buffer:
                raise FuseOSError(errno.ENOENT)
            return 0

        def read(self, path, size, offset, fh):
            nombre = path.lstrip('/')
            with cerrojo:
                entrada = self._entrada_por_nombre(nombre)
                if entrada is not None:
                    with open(self.ruta, 'rb') as imagen:
                        imagen.seek(entrada.cluster_inicial * TAMANIO_CLUSTER + offset)
                        disponibles = max(0, entrada.tamanio - offset)
                        return imagen.read(min(size, disponibles))
            with self._cerrojo_buffers:
                if path in self._buffers:
                    return bytes(self._buffers[path][offset:offset + size])
            raise FuseOSError(errno.ENOENT)

        # -------- Escritura (cp, > archivo, etc.) --------

        def create(self, path, mode, fi=None):
            nombre = path.lstrip('/')
            if len(nombre) > LONGITUD_NOMBRE:
                raise FuseOSError(errno.ENAMETOOLONG)
            with self._cerrojo_buffers:
                self._buffers[path] = bytearray()
            return 0

        def write(self, path, data, offset, fh):
            with self._cerrojo_buffers:
                buf = self._buffers.setdefault(path, bytearray())
                fin = offset + len(data)
                if fin > len(buf):
                    buf.extend(b'\x00' * (fin - len(buf)))
                buf[offset:fin] = data
            return len(data)

        def truncate(self, path, length, fh=None):
            with self._cerrojo_buffers:
                if path in self._buffers:
                    buf = self._buffers[path]
                    if length < len(buf):
                        del buf[length:]
                    else:
                        buf.extend(b'\x00' * (length - len(buf)))
                    return 0
            # No soportamos truncar archivos ya persistidos en el FS;
            # el modelo de asignación contigua no lo permite sin reubicar.
            raise FuseOSError(errno.EACCES)

        def release(self, path, fh):
            with self._cerrojo_buffers:
                contenido = self._buffers.pop(path, None)
            if contenido is None or len(contenido) == 0:
                return 0
            nombre = path.lstrip('/')
            try:
                _escribir_en_fs(self.ruta, nombre, bytes(contenido))
            except ValueError as err:
                # En este punto FUSE ya devolvió éxito al write(),
                # así que solo podemos avisar al log del sistema.
                print(f'Aviso: no pude persistir «{nombre}»: {err}',
                      file=sys.stderr)
                raise FuseOSError(errno.EIO)
            return 0

        # -------- Borrado --------

        def unlink(self, path):
            nombre = path.lstrip('/')
            try:
                with cerrojo:
                    entradas = leer_directorio(self.ruta)
                    entrada = _buscar_entrada(entradas, nombre)
                    nombre_invalido = bytes([RELLENO_NOMBRE_LIBRE] * LONGITUD_NOMBRE)
                    with open(self.ruta, 'r+b') as imagen:
                        imagen.seek(entrada.offset_en_disco + OFFSET_TIPO)
                        imagen.write(TIPO_ENTRADA_LIBRE)
                        imagen.seek(entrada.offset_en_disco + OFFSET_NOMBRE)
                        imagen.write(nombre_invalido)
            except ValueError:
                raise FuseOSError(errno.ENOENT)
            return 0

        # -------- No-ops para que cp, touch, etc. no se quejen --------

        def chmod(self, path, mode):
            return 0

        def chown(self, path, uid, gid):
            return 0

        def utimens(self, path, times=None):
            return 0

    if not os.path.isdir(punto_montaje):
        raise ValueError(
            f'El punto de montaje «{punto_montaje}» no existe o no es un directorio.'
        )

    print(f'Montando «{ruta_imagen}» en «{punto_montaje}». '
          'Usa Ctrl+C o «fusermount -u <ruta>» para desmontar.')
    FUSE(FiUnamFS(ruta_imagen), punto_montaje, foreground=True, nothreads=False)


# ---------------------------------------------------------------------------
# Ejecución concurrente
# ---------------------------------------------------------------------------
def _ejecutar_en_hilo(funcion, *args) -> None:
    """Lanza la operación en un hilo y propaga cualquier excepción al main."""
    contenedor: dict = {}

    def envoltura():
        try:
            funcion(*args)
        except Exception as err:
            contenedor['error'] = err

    hilo = threading.Thread(target=envoltura)
    hilo.start()
    hilo.join()
    if 'error' in contenedor:
        raise contenedor['error']


# ---------------------------------------------------------------------------
# Modo interactivo
# ---------------------------------------------------------------------------
_BANNER = """
======================================================
            FiUnamFS — modo interactivo
======================================================
  1) Listar archivos
  2) Extraer archivo  (FiUnamFS → equipo local)
  3) Insertar archivo (equipo local → FiUnamFS)
  4) Eliminar archivo
  5) Salir
"""


def _menu_interactivo(ruta: str) -> None:
    while True:
        print(_BANNER)
        try:
            opcion = input('Elige una opción [1-5]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nHasta luego.')
            return

        try:
            if opcion == '1':
                _ejecutar_en_hilo(listar, ruta)
            elif opcion == '2':
                nombre = input('Nombre del archivo en FiUnamFS: ').strip()
                destino = input('Ruta de destino local: ').strip()
                _ejecutar_en_hilo(extraer, ruta, nombre, destino)
            elif opcion == '3':
                local = input('Ruta del archivo local: ').strip()
                _ejecutar_en_hilo(insertar, ruta, local)
            elif opcion == '4':
                nombre = input('Nombre del archivo a eliminar: ').strip()
                _ejecutar_en_hilo(eliminar, ruta, nombre)
            elif opcion == '5':
                print('Hasta luego.')
                return
            else:
                print('Opción no reconocida.')
        except (ValueError, FileNotFoundError) as err:
            print(f'Error: {err}')


# ---------------------------------------------------------------------------
# CLI con argparse
# ---------------------------------------------------------------------------
def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='proyecto.py',
        description='Herramienta para manipular imágenes FiUnamFS (versión 26-2).',
        epilog='Sin subcomando se entra al modo interactivo.',
    )
    parser.add_argument('imagen', help='Ruta a la imagen FiUnamFS (1440 KB).')
    sub = parser.add_subparsers(dest='comando')

    sub.add_parser('listar', help='Lista el contenido del directorio.')

    p_ext = sub.add_parser('extraer', help='Copia un archivo al equipo local.')
    p_ext.add_argument('nombre', help='Nombre del archivo dentro de FiUnamFS.')
    p_ext.add_argument('destino', help='Ruta local o directorio destino.')

    p_ins = sub.add_parser('insertar', help='Copia un archivo local a FiUnamFS.')
    p_ins.add_argument('ruta_local', help='Archivo local a insertar.')

    p_del = sub.add_parser('eliminar', help='Borrado lógico de un archivo.')
    p_del.add_argument('nombre', help='Nombre del archivo a eliminar.')

    sub.add_parser('menu', help='Inicia el modo interactivo.')

    p_mnt = sub.add_parser(
        'mount',
        help='Monta la imagen como un directorio (requiere fusepy y libfuse).',
    )
    p_mnt.add_argument(
        'punto_montaje',
        help='Directorio donde montar el FiUnamFS (debe existir y estar vacío).',
    )

    return parser


def main() -> int:
    args = _construir_parser().parse_args()

    try:
        validar_imagen(args.imagen)

        if args.comando in (None, 'menu'):
            _menu_interactivo(args.imagen)
        elif args.comando == 'listar':
            _ejecutar_en_hilo(listar, args.imagen)
        elif args.comando == 'extraer':
            _ejecutar_en_hilo(extraer, args.imagen, args.nombre, args.destino)
        elif args.comando == 'insertar':
            _ejecutar_en_hilo(insertar, args.imagen, args.ruta_local)
        elif args.comando == 'eliminar':
            _ejecutar_en_hilo(eliminar, args.imagen, args.nombre)
        elif args.comando == 'mount':
            _montar_fuse(args.imagen, args.punto_montaje)
    except (FileNotFoundError, ValueError, RuntimeError) as err:
        print(f'Error: {err}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
