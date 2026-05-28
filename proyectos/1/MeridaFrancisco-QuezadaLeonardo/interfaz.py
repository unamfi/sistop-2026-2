# interfaz.py
# Interfaz gráfica simple para usar FiUnamFS sin escribir comandos.

import os
import tkinter as tk

from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog

from imagen_fiunamfs import ImagenFiUnamFS
from trabajador import TrabajadorFS


class InterfazFiUnamFS:
    def __init__(self, ventana, ruta_imagen):
        self.ventana = ventana
        self.ventana.title("FiUnamFS")
        self.ventana.geometry("500x400")

        self.fs = ImagenFiUnamFS(ruta_imagen)
        self.trabajador = TrabajadorFS(self.fs)

        self.archivos_actuales = []

        self.crear_interfaz()

        self.trabajador.enviar_tarea("listar")
        self.ventana.after(200, self.revisar_respuestas)

    def crear_interfaz(self):
        titulo = tk.Label(
            self.ventana,
            text="Administrador FiUnamFS",
            font=("Arial", 14)
        )
        titulo.pack(pady=10)

        self.lista = tk.Listbox(
            self.ventana,
            width=60,
            height=12
        )
        self.lista.pack(padx=10, pady=10)

        frame_botones = tk.Frame(self.ventana)
        frame_botones.pack(pady=5)

        tk.Button(
            frame_botones,
            text="Actualizar",
            command=self.actualizar
        ).grid(row=0, column=0, padx=5, pady=5)

        tk.Button(
            frame_botones,
            text="Extraer",
            command=self.extraer
        ).grid(row=0, column=1, padx=5, pady=5)

        tk.Button(
            frame_botones,
            text="Copiar al FS",
            command=self.copiar
        ).grid(row=1, column=0, padx=5, pady=5)

        tk.Button(
            frame_botones,
            text="Eliminar",
            command=self.eliminar
        ).grid(row=1, column=1, padx=5, pady=5)

        self.estado = tk.Label(
            self.ventana,
            text="Listo.",
            anchor="w"
        )
        self.estado.pack(fill=tk.X, padx=10, pady=10)

    def actualizar(self):
        self.estado.config(text="Actualizando lista...")
        self.trabajador.enviar_tarea("listar")

    def obtener_archivo_seleccionado(self):
        seleccion = self.lista.curselection()

        if not seleccion:
            messagebox.showwarning("Aviso", "Selecciona un archivo.")
            return None

        indice = seleccion[0]
        return self.archivos_actuales[indice]["nombre"]

    def extraer(self):
        nombre = self.obtener_archivo_seleccionado()

        if nombre is None:
            return

        ruta_salida = filedialog.asksaveasfilename(
            title="Guardar archivo como",
            initialfile=nombre
        )

        if not ruta_salida:
            return

        self.estado.config(text="Extrayendo archivo...")

        self.trabajador.enviar_tarea(
            "extraer",
            {
                "nombre_fs": nombre,
                "ruta_salida": ruta_salida
            }
        )

    def copiar(self):
        ruta_local = filedialog.askopenfilename(
            title="Selecciona un archivo"
        )

        if not ruta_local:
            return

        nombre_sugerido = os.path.basename(ruta_local)

        nombre_fs = simpledialog.askstring(
            "Nombre del archivo",
            "Nombre dentro de FiUnamFS:",
            initialvalue=nombre_sugerido
        )

        if not nombre_fs:
            return

        self.estado.config(text="Copiando archivo...")

        self.trabajador.enviar_tarea(
            "copiar",
            {
                "ruta_local": ruta_local,
                "nombre_fs": nombre_fs
            }
        )

    def eliminar(self):
        nombre = self.obtener_archivo_seleccionado()

        if nombre is None:
            return

        confirmar = messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar {nombre}?"
        )

        if not confirmar:
            return

        self.estado.config(text="Eliminando archivo...")

        self.trabajador.enviar_tarea(
            "eliminar",
            {
                "nombre_fs": nombre
            }
        )

    def revisar_respuestas(self):
        respuesta = self.trabajador.obtener_respuesta()

        while respuesta is not None:
            tipo, datos = respuesta

            if tipo == "listar_ok":
                self.archivos_actuales = datos
                self.lista.delete(0, tk.END)

                for archivo in datos:
                    texto = f"{archivo['nombre']} ({archivo['tamanio']} bytes)"
                    self.lista.insert(tk.END, texto)

                self.estado.config(text="Lista actualizada.")

            elif tipo == "operacion_ok":
                messagebox.showinfo("Operación realizada", datos)
                self.estado.config(text=datos)
                self.trabajador.enviar_tarea("listar")

            elif tipo == "error":
                messagebox.showerror("Error", datos)
                self.estado.config(text="Error en la operación.")

            respuesta = self.trabajador.obtener_respuesta()

        self.ventana.after(200, self.revisar_respuestas)

    def cerrar(self):
        self.trabajador.detener()
        self.fs.cerrar()
        self.ventana.destroy()


def main():
    ruta_imagen = "fiunamfs.img"

    ventana = tk.Tk()
    app = InterfazFiUnamFS(ventana, ruta_imagen)

    ventana.protocol("WM_DELETE_WINDOW", app.cerrar)
    ventana.mainloop()


if __name__ == "__main__":
    main()