"""
Manejo de la lectura binaria sobre la imagen de FiUnamFS
"""

"""
representacion de el archivo .img usado como pseudodisco
"""
class Disco:
    def __init__(self, ruta_imagen):
        self.ruta_imagen = ruta_imagen
    
    """
    lectura de una cantidad de bytes a partir de un desplazamiento especifico
    """
    def leer_bytes(self, desplazamiento, cantidad):
        
        with open(self.ruta_imagen, "rb") as imagen:
            imagen.seek(desplazamiento)
            return imagen.read(cantidad)
    
    """
    escritura de bytes en la imagen a partir de un desplazamiento
    """
    def escribir_bytes(self, desplazamiento, datos):
        with open(self.ruta_imagen, "r+b") as imagen:
            imagen.seek(desplazamiento)
            imagen.write(datos)
