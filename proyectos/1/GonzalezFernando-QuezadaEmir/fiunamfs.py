from functions import (
    superbloque, directorio, imprimir_archivos,
    extraer, paste, borrar, clusters_ocupados,
)
from pathlib import Path

class FiUnamFS:
    # La clase FiUnamFS encapsula todas las operaciones sobre el .img.
    def __init__(self, img_path):
        self.img_path = img_path
        self._validar()

    # Métodos internos
    def _leer(self):
        # Método que lee el .img completo y lo devuelve como bytearray.
        with open(self.img_path, 'rb') as f:
            return bytearray(f.read())

    def _validar(self):
        # Verificamos que el .img exista y sea válido, de lo contrario levantamos una alerta.
        if not Path(self.img_path).exists():
            raise FileNotFoundError(f"Archivo no encontrado: {self.img_path}")
        info = superbloque(self._leer())
        if info['fileName'] != 'FiUnamFS':
            raise ValueError("El archivo no es un sistema FiUnamFS válido.")
        if info['version'] != '26-2':
            print(f"Advertencia: versión '{info['version']}', se esperaba '26-2'.")

    # Métodos públicos

    def listar(self, imprimir=True):
        # Est método lista los archivos del directorio.
        # FUSE -> readdir()

        # Args:
            # imprimir: Si True, imprime la tabla en pantalla.
        # Returns:
            # Lista de entradas crudas del directorio (bytearray de 64 bytes c/u).

        data     = self._leer()
        info     = superbloque(data)
        archivos = directorio(data, info)

        if imprimir:
            print(f"Volumen: {info['volumen']}  |  Versión: {info['version']}")
            print(f"Clusters totales: {info['clusters_unidad']}  |  "
                  f"Tamaño de cluster: {info['cluster_size']} bytes\n")
            imprimir_archivos(archivos)
        return archivos

    def extraer(self, filename, nombre_salida=None):
        # Método que copia un archivo de FiUnamFS al sistema local (host).
        # FUSE -> open() + read()

        # Args:
            # filename: Nombre del archivo dentro de FiUnamFS.
            # nombre_salida: Ruta de destino local (opcional).
        # Returns:
            # True si tuvo éxito, False si falló.
        
        data = self._leer()
        return extraer(data, filename, nombre_salida)

    def extraer_datos(self, filename):
        # Este método devuelve el contenido de un solo archivo en especifico
        # como bytes, sin escribirlo a disco.
        # FUSE -> read()  

        # Args:
            # filename: Nombre del archivo dentro de FiUnamFS.
        # Returns:
            # bytes con el contenido, o None si no se encontró.
 
        from functions import find_file 

        data      = self._leer()
        info      = superbloque(data)
        file_info = find_file(data, filename, info)
        if file_info is None:
            return None
        start = file_info['start_cluster'] * info['cluster_size']
        end   = start + file_info['size']
        return bytes(data[start:end])

    def pegar(self, archivo_local, nombre_destino=None):
        # Como su nombre lo indica, copia un archivo del sistema local a FiUnamFS.
        # FUSE -> create() + write()

        # Args:
            # archivo_local: Ruta al archivo en el sistema local.
            # Se recomienda poner la ruta entre comillas "C:ejemplo\..." para evitar errores.

            # nombre_destino: Nombre con el que se guardará en FiUnamFS (opcional).
        # Returns:
            # True si tuvo éxito, False si falló.

        return paste(self.img_path, archivo_local, nombre_destino)

    def borrar(self, filename):
        # Elimina un archivo específico dentro de fiunamfs.img
        # FUSE -> unlink()

        # Args:
            # filename: Nombre del archivo a eliminar.
        # Returns:
            # True si tuvo éxito, False si falló.

        return borrar(self.img_path, filename)

    def estado_disco(self):
        # Reliza un diagnóstico del estado actual del disco (fiunamfs.img).
        # FUSE -> statfs()

        # Returns:
            # Diccionario con clusters_totales, clusters_libres, num_archivos, volumen.
        
        data     = self._leer()
        info     = superbloque(data)
        archivos = directorio(data, info)
        ocupados = clusters_ocupados(archivos)
        # Los clusters 0-8 son del sistema (superbloque + directorio)
        libres   = info['clusters_unidad'] - 9 - len(ocupados)
        return {
            'volumen':          info['volumen'],
            'clusters_totales': info['clusters_unidad'],
            'clusters_libres':  max(libres, 0),
            'num_archivos':     len(archivos),
        }
