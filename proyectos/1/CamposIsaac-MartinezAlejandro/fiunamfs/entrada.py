#!/usr/bin/python3

#Programa encargado de leer entradas del directorio
#Autores: Isaac Campos, Alejandro Martinez
#Fecha de realización: 17 Mayo 2026

from . import herramientas as h 

#Constantes para identificar el tipo de entrada conforme al planteamiento.
#Un archivo válido usa '-', mientras que una entrada libre usa '/'.

ARCHIVO_VAL = '-'
ARCHIVO_VACIO = '/'
NOMBRE_VACIO = '###############'

#Se define la clase para los archivos.
#Cada objeto de esta clase representa una entrada de 64 bytes dentro del directorio.

#En este proyecto, una entrada del directorio representa la información de un archivo:
#tipo, nombre, tamaño, cluster inicial y fechas de creación/modificación.

class EntradaDir:

    def __init__(self, bytes_raw):

        if bytes_raw is None:
            #Cuando no se reciben bytes, se crea una entrada vacía con los valores por defecto.
            self.tipo_archivo = ARCHIVO_VACIO
            self.nombre_archivo = NOMBRE_VACIO
            self.tam_archivo = 0
            self.cluster_incial = 0
            self.hf_creado = '00000000000000'
            self.hf_modificado = '00000000000000'
        else:
            self.parsear(bytes_raw)

    #Interpreta los bytes de una entrada del directorio según la estructura de FiUnamFS.
    #Los campos numéricos se leen en little endian mediante las funciones auxiliares.
    
    def parsear(self,bytes_raw):

        self.tipo_archivo = chr(bytes_raw[0])
        self.nombre_archivo = bytes_raw[1:16].decode('ascii').strip('\x00').strip()
        self.tam_archivo = h.leerLe(bytes_raw[16:20])
        self.cluster_incial = h.leerLe(bytes_raw[20:24])
        self.hf_creado = bytes_raw[30:44].decode('ascii').strip('\x00').strip()
        self.hf_modificado = bytes_raw[50:64].decode('ascii').strip('\x00').strip()

    #Crea una nueva entrada válida para un archivo que se agregará al sistema.
    #El nombre se limita a 15 caracteres, como lo establece el formato de FiUnamFS.
    
    def crearNuevo(self, nombre, tam, inicio):

        self.tipo_archivo = ARCHIVO_VAL
        self.nombre_archivo = nombre[:15].ljust(15, '\x00')
        self.tam_archivo  = tam
        self.cluster_incial = inicio
        self.hf_creado = h.obtenerFechaHora()
        self.hf_modificado = h.obtenerFechaHora()
    
    #Elimina lógicamente una entrada del directorio.
    #No borra necesariamente los datos físicos del archivo, solo marca la entrada como libre.
    
    def eliminar(self):
        self.tipo_archivo = ARCHIVO_VACIO
        self.nombre_archivo = NOMBRE_VACIO
        self.tam_archivo = 0
        self.cluster_incial = 0
        self.hf_creado = '00000000000000'
        self.hf_modificado = '00000000000000'

    #Convierte la información de la entrada nuevamente a bytes.
    #Esto permite escribir el directorio actualizado dentro de la imagen del disco.

    def pasarBytes(self):
        datos = b''
        datos += self.tipo_archivo.encode('ascii')  
        datos += self.nombre_archivo.encode('ascii')[0:15].ljust(15, b'\x00')
        datos += h.escribirLe(self.tam_archivo)
        datos += h.escribirLe(self.cluster_incial)
        datos += b'\x00' * 6
        datos += self.hf_creado.encode('ascii')[0:14].ljust(14, b'\x00')
        datos += b'\x00' * 6
        datos += self.hf_modificado.encode('ascii')[0:14].ljust(14, b'\x00')

        return bytes(datos)