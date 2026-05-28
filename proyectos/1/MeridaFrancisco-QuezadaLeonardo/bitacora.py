# bitacora.py

class BitacoraFS:
    
    def __init__(self):
        self.archivos_leidos = 0
        self.archivos_escritos = 0
        self.archivos_eliminados = 0
        self.ultimo_movimiento = ""

    def registrar_lectura(self, mensaje):
        self.archivos_leidos += 1
        self.ultimo_movimiento = mensaje

    def registrar_escritura(self, mensaje):
        self.archivos_escritos += 1
        self.ultimo_movimiento = mensaje

    def registrar_eliminacion(self, mensaje):
        self.archivos_eliminados += 1
        self.ultimo_movimiento = mensaje