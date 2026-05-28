import math
import os
import queue
import threading

from .directory import Directory, DirectoryEntry
from .disk import CLUSTER_SIZE, FiUnamFSDisk
from .exceptions import FilesystemError
from .superblock import Superblock


class FiUnamFS:
    def __init__(self, disk: FiUnamFSDisk) -> None:
        self.disk = disk
        self.superblock = Superblock(disk)
        self.directory = Directory(disk, self.superblock)

    # --- Fase 3 ---
    def ls(self) -> None:
        files = self.directory.list_files()
        if not files:
            print("(directorio vacío)")
            return
        header = f"{'Nombre':<15}  {'Tamaño':>10}  {'C.Inicio':>8}  Modificado"
        print(header)
        print('-' * len(header))
        for e in files:
            mtime = e.modified_at if e.modified_at else '?'
            print(
                f"{e.name:<15}  {e.size:>10} B  "
                f"{e.start_cluster:>8}  {mtime}"
            )

    def cp_out(self, fs_name: str, host_path: str) -> None:
        entry = self.directory.find(fs_name)
        if entry is None:
            raise FilesystemError(f"Archivo no encontrado: '{fs_name}'")

        # Cola sin límite de tamaño: el disco máximo es 1.4 MB, así que el lector
        # puede adelantarse sin riesgo y evitamos deadlocks si el escritor falla.
        q: queue.Queue[bytes | None] = queue.Queue()

        # Lista mutable porque las closures no pueden reasignar variables del scope
        # padre — con .append() sí podemos escribir en ella desde los hilos hijos.
        errores: list[Exception] = []
        abortar = threading.Event()

        def lector() -> None:
            try:
                remaining = entry.size
                for c in range(
                    entry.start_cluster,
                    entry.start_cluster + entry.clusters_needed(),
                ):
                    if abortar.is_set():
                        break
                    bloque = self.disk.read_cluster(c)
                    # bloque[:remaining] recorta el padding nulo del último cluster;
                    # cuando remaining > CLUSTER_SIZE Python devuelve el slice completo.
                    q.put_nowait(bloque[:remaining])
                    remaining -= CLUSTER_SIZE
            except Exception as exc:
                errores.append(exc)
            finally:
                q.put_nowait(None)  # centinela: le dice al escritor que ya no hay más

        def escritor() -> None:
            try:
                with open(host_path, 'wb') as out:
                    while True:
                        chunk = q.get()
                        if chunk is None:
                            break
                        out.write(chunk)
            except Exception as exc:
                errores.append(exc)
                abortar.set()  # le pide al lector que deje de producir

        t_lector = threading.Thread(target=lector, daemon=True, name='cp_out-lector')
        t_escritor = threading.Thread(target=escritor, daemon=True, name='cp_out-escritor')
        t_lector.start()
        t_escritor.start()
        t_lector.join()
        t_escritor.join()

        if errores:
            raise errores[0]

    # --- Fase 4 ---
    def cp_in(self, host_path: str, fs_name: str) -> None:
        if not os.path.exists(host_path):
            raise FilesystemError(f"Archivo no encontrado: '{host_path}'")

        size = os.path.getsize(host_path)

        if self.directory.find(fs_name) is not None:
            raise FilesystemError(f"'{fs_name}' ya existe en el sistema")

        clusters_needed = math.ceil(size / CLUSTER_SIZE) if size else 0

        start = self.directory.find_contiguous_clusters(clusters_needed)
        if start is None:
            raise FilesystemError(
                "Espacio contiguo insuficiente. "
                "Sugerencia: intente ejecutar -defrag"
            )

        entry = DirectoryEntry.new_file(fs_name, size, start)
        self.directory.add_entry(entry)

        q: queue.Queue[bytes | None] = queue.Queue()
        errores: list[Exception] = []
        abortar = threading.Event()

        def lector() -> None:
            try:
                with open(host_path, 'rb') as src:
                    for _ in range(clusters_needed):
                        if abortar.is_set():
                            break
                        chunk = src.read(CLUSTER_SIZE)
                        # El último chunk puede ser menor que CLUSTER_SIZE; se rellena
                        # con ceros para respetar la alineación de cluster del disco.
                        q.put_nowait(chunk.ljust(CLUSTER_SIZE, b'\x00'))
            except Exception as exc:
                errores.append(exc)
            finally:
                q.put_nowait(None)

        def escritor() -> None:
            try:
                current_cluster = start
                while True:
                    data = q.get()
                    if data is None:
                        break
                    self.disk.write_cluster(current_cluster, data)
                    current_cluster += 1
            except Exception as exc:
                errores.append(exc)
                abortar.set()

        t_lector = threading.Thread(target=lector, daemon=True, name='cp_in-lector')
        t_escritor = threading.Thread(target=escritor, daemon=True, name='cp_in-escritor')
        t_lector.start()
        t_escritor.start()
        t_lector.join()
        t_escritor.join()

        if errores:
            raise errores[0]

    # --- Fase 5 ---
    def rm(self, fs_name: str) -> None:
        if self.directory.find(fs_name) is None:
            raise FilesystemError(f"Archivo no encontrado: '{fs_name}'")
        self.directory.delete_entry(fs_name)

    def defrag(self) -> None:
        files = sorted(
            self.directory.list_files(), key=lambda e: e.start_cluster
        )
        current_free_cluster = self.superblock.data_start_cluster

        for entry in files:
            n = entry.clusters_needed()
            if entry.start_cluster != current_free_cluster:
                for i in range(n):
                    block = self.disk.read_cluster(entry.start_cluster + i)
                    self.disk.write_cluster(current_free_cluster + i, block)
                entry.start_cluster = current_free_cluster
                self.directory.update_entry(entry)
            current_free_cluster += n

        null_cluster = b'\x00' * CLUSTER_SIZE
        for c in range(current_free_cluster, self.superblock.total_clusters):
            self.disk.write_cluster(c, null_cluster)
