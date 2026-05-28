# trabajador.py
# Hilo auxiliar para que la interfaz no haga directamente las operaciones pesadas.

import threading
import queue


class TrabajadorFS:
    def __init__(self, sistema_archivos):
        self.fs = sistema_archivos

        # La interfaz manda tareas a esta cola.
        self.tareas = queue.Queue()

        # El trabajador responde por esta otra cola.
        self.respuestas = queue.Queue()

        self.activo = True

        self.hilo = threading.Thread(
            target=self._procesar_tareas,
            daemon=True
        )

        self.hilo.start()

    def enviar_tarea(self, accion, datos=None):
        if datos is None:
            datos = {}

        self.tareas.put((accion, datos))

    def obtener_respuesta(self):
        try:
            return self.respuestas.get_nowait()
        except queue.Empty:
            return None

    def detener(self):
        self.activo = False
        self.tareas.put(("salir", {}))

    def _procesar_tareas(self):
        while self.activo:
            accion, datos = self.tareas.get()

            try:
                if accion == "listar":
                    archivos = self.fs.listar_archivos()

                    resultado = []
                    for archivo in archivos:
                        resultado.append({
                            "nombre": archivo.nombre,
                            "tamanio": archivo.tamanio,
                            "cluster": archivo.cluster_inicial,
                            "creacion": archivo.fecha_creacion,
                            "modificacion": archivo.fecha_modificacion
                        })

                    self.respuestas.put(("listar_ok", resultado))

                elif accion == "extraer":
                    self.fs.extraer_archivo(
                        datos["nombre_fs"],
                        datos["ruta_salida"]
                    )

                    self.respuestas.put((
                        "operacion_ok",
                        f"Archivo '{datos['nombre_fs']}' extraído correctamente."
                    ))

                elif accion == "copiar":
                    self.fs.copiar_a_fiunamfs(
                        datos["ruta_local"],
                        datos["nombre_fs"]
                    )

                    self.respuestas.put((
                        "operacion_ok",
                        f"Archivo '{datos['nombre_fs']}' copiado correctamente."
                    ))

                elif accion == "eliminar":
                    self.fs.eliminar_archivo(datos["nombre_fs"])

                    self.respuestas.put((
                        "operacion_ok",
                        f"Archivo '{datos['nombre_fs']}' eliminado correctamente."
                    ))

                elif accion == "salir":
                    break

            except Exception as e:
                self.respuestas.put(("error", str(e)))