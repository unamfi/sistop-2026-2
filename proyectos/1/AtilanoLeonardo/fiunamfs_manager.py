import os
import struct
import threading
import queue
import time
import sys

TAM_CLUSTER = 2048
OFFSET_DIR = 2048
MAX_ENTRIES = 256  # (8 clusters de dir * 2048) / 64 bytes


class FSWorker(threading.Thread):
    def __init__(self, disco_img):
        super().__init__()
        self.disco = disco_img
        self.cola_tareas = queue.Queue()
        self.daemon = True

    def run(self):
        while True:
            tarea = self.cola_tareas.get()
            if tarea is None:
                break

            accion, argumentos, evento_resp, resultado = tarea
            try:
                with open(self.disco, 'r+b') as f:
                    self._verificar_disco(f)

                    if accion == 'listar':
                        resultado['data'] = self._listar(f)
                    elif accion == 'sacar':
                        self._sacar_archivo(f, argumentos['origen'], argumentos['destino'])
                    elif accion == 'meter':
                        self._meter_archivo(f, argumentos['origen'], argumentos['destino'])
                    elif accion == 'borrar':
                        self._borrar_archivo(f, argumentos['objetivo'])
            except Exception as e:
                # print("Hubo un error interno:", e)
                resultado['error'] = str(e)

            evento_resp.set()

    def _verificar_disco(self, f):
        f.seek(5)
        # Cambiado a latin-1 para soportar 8-bits
        nombre = f.read(8).decode('latin-1')
        f.seek(14)
        version = f.read(4).decode('latin-1')
        if nombre != "FiUnamFS" or version not in ["26-2", "24-2"]:
            raise ValueError("No es un disco FiUnamFS valido.")

    def _listar(self, f):
        archivos = []
        f.seek(OFFSET_DIR)
        for i in range(MAX_ENTRIES):
            pos = OFFSET_DIR + (i * 64)
            f.seek(pos)
            data = f.read(64)
            if data[0:1] == b'-':
                # Cambiado a latin-1
                nom = data[1:16].decode('latin-1').strip(' \x00')
                tam = struct.unpack('<I', data[16:20])[0]
                clust = struct.unpack('<I', data[20:24])[0]
                # Cambiado a latin-1
                fecha_m = data[50:64].decode('latin-1')
                archivos.append({
                    'nombre': nom, 'tamano': tam, 'cluster': clust,
                    'modificado': fecha_m, 'offset': pos
                })
        return archivos

    def _sacar_archivo(self, f, nom_src, ruta_dst):
        lista = self._listar(f)
        for arch in lista:
            if arch['nombre'] == nom_src:
                f.seek(arch['cluster'] * TAM_CLUSTER)
                info = f.read(arch['tamano'])
                # Escribir a la compu
                out_f = open(ruta_dst, 'wb')
                out_f.write(info)
                out_f.close()
                return
        raise FileNotFoundError("No encontre ese archivo en el FiUnamFS.")

    def _meter_archivo(self, f, ruta_host, nom_fs):
        if not os.path.exists(ruta_host):
            raise Exception("No existe el archivo en tu PC.")

        tam_bytes = os.path.getsize(ruta_host)
        req_clusters = max(1, (tam_bytes + TAM_CLUSTER - 1) // TAM_CLUSTER)

        mapa_clusters = [False] * 720
        for i in range(9):
            mapa_clusters[i] = True

        lista = self._listar(f)
        for arch in lista:
            c_ini = arch['cluster']
            c_fin = c_ini + max(1, (arch['tamano'] + TAM_CLUSTER - 1) // TAM_CLUSTER)
            for j in range(c_ini, c_fin):
                if j < 720:
                    mapa_clusters[j] = True

        cluster_libre = -1
        contador = 0
        for i in range(9, 720):
            if not mapa_clusters[i]:
                contador += 1
                if contador == req_clusters:
                    cluster_libre = i - req_clusters + 1
                    break
            else:
                contador = 0

        if cluster_libre == -1:
            raise Exception("No hay espacio contiguo en el disco.")

        pos_dir = -1
        for i in range(MAX_ENTRIES):
            offset = OFFSET_DIR + (i * 64)
            f.seek(offset)
            if f.read(1) in [b'/', b'\x00']:
                pos_dir = offset
                break

        if pos_dir == -1:
            raise Exception("Directorio lleno.")

        with open(ruta_host, 'rb') as hf:
            datos_nuevos = hf.read()

        f.seek(cluster_libre * TAM_CLUSTER)
        f.write(datos_nuevos)

        # Cambiado a latin-1
        ahora = time.strftime('%Y%m%d%H%M%S').encode('latin-1')
        nombre_bytes = nom_fs[:15].encode('latin-1').ljust(15, b' ')

        entrada = bytearray(64)
        entrada[0:1] = b'-'
        entrada[1:16] = nombre_bytes
        entrada[16:20] = struct.pack('<I', tam_bytes)
        entrada[20:24] = struct.pack('<I', cluster_libre)
        entrada[30:44] = ahora
        entrada[50:64] = ahora

        f.seek(pos_dir)
        f.write(entrada)

    def _borrar_archivo(self, f, nombre):
        lista = self._listar(f)
        flag_borrado = False
        for arch in lista:
            if arch['nombre'] == nombre:
                f.seek(arch['offset'])
                f.write(b'/')
                f.write(b'###############')
                flag_borrado = True
                break

        if not flag_borrado:
            raise Exception("El archivo a borrar no existe.")


# funcion wrapper para mandar cosas a la cola
def despachar(worker, accion, args={}):
    evt = threading.Event()
    res = {}
    worker.cola_tareas.put((accion, args, evt, res))
    evt.wait()

    if 'error' in res:
        print(f"Error: {res['error']}")
        return False
    return res.get('data', True)


def main():
    img = "fiunamfs.img"
    if not os.path.exists(img):
        print("Falta el archivo fiunamfs.img aqui.")
        sys.exit(1)

    hilo_fs = FSWorker(img)
    hilo_fs.start()

    opc = ""
    while opc != "5":
        print("\n--- FiUnamFS Manager ---")
        print("1. Listar")
        print("2. Copiar a mi PC")
        print("3. Inyectar al disco")
        print("4. Borrar archivo")
        print("5. Salir")

        opc = input("Opcion: ")

        if opc == '1':
            datos = despachar(hilo_fs, 'listar')
            if datos is not False:
                print("\nNombre\t\tTamaño\tCluster\tModificacion")
                print("-" * 50)
                for d in datos:
                    print(f"{d['nombre']}\t{d['tamano']}\t{d['cluster']}\t{d['modificado']}")

        elif opc == '2':
            s = input("Archivo origen (en disco): ")
            d = input("Ruta destino (en pc): ")
            if despachar(hilo_fs, 'sacar', {'origen': s, 'destino': d}):
                print("Listo, se copio a tu PC.")

        elif opc == '3':
            s = input("Ruta origen (en pc): ")
            d = input("Nombre destino (max 15): ")
            if despachar(hilo_fs, 'meter', {'origen': s, 'destino': d}):
                print("Se metio el archivo al FiUnamFS.")

        elif opc == '4':
            t = input("Archivo a borrar: ")
            if despachar(hilo_fs, 'borrar', {'objetivo': t}):
                print("Borrado correctamente.")

        elif opc == '5':
            hilo_fs.cola_tareas.put(None)
            hilo_fs.join()
            print("Adios!")


if __name__ == "__main__":
    main()