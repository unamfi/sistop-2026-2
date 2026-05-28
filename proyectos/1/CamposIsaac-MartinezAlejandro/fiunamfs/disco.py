#!/usr/bin/python3

#Programa encargado de realizar operaciones sobre el disco entero
#Autores: Isaac Campos, Alejandro Martinez
#Fecha de realización: 18 Mayo 2026

from .superbloque import SuperBloque
from .entrada import EntradaDir
from . import herramientas as h 
import threading

#Constantes usadas para recorrer las entradas del directorio.
#Cada entrada ocupa 64 bytes y '/' indica una entrada disponible.
TAM_ENTRADA_DIR = 64
ARCHIVO_VACIO = '/'


#Se define la clase para el disco.
#Esta clase concentra las operaciones principales sobre la imagen FiUnamFS:
#cargar el directorio, leer archivos, escribir archivos, eliminar entradas y sincronizar cambios.

class Disco:

    def __init__(self,ruta_img):
        self.ruta_img = ruta_img
        self.superbloque = SuperBloque(self.ruta_img)
        self.cargarDirectorio()
        self.lock = threading.RLock()
        self.condicion = threading.Condition(self.lock)
        self.operaciones = []
        self.hilo = threading.Thread(
        target=self.hiloEscritura,daemon=True)
        self.hilo.start()

    #Carga todas las entradas del directorio desde la imagen.
    #El directorio se lee como un bloque de bytes y después se divide en entradas de 64 bytes.
    def cargarDirectorio(self):
        with open(self.ruta_img, 'rb') as img:
            img.seek(self.superbloque.desp_dir)
            datos = img.read(self.superbloque.tam_dir)
        
        self.entradas = []
        for i in range(0, len(datos), TAM_ENTRADA_DIR):
            pedazo_entrada = datos[i:i+TAM_ENTRADA_DIR]
            entrada = EntradaDir(pedazo_entrada)
            self.entradas.append(entrada)
    
    #Devuelve únicamente los nombres de las entradas que representan archivos válidos.
    #Las entradas marcadas con '/' se consideran libres y no se muestran.

    def listarEntradas(self):
        no_vacias = []
        for entrada in self.entradas:
            if entrada.tipo_archivo != '/':
                no_vacias.append(entrada.nombre_archivo.strip())
        return no_vacias
    
    #Busca una entrada por nombre dentro del directorio cargado en memoria.
    #Se eliminan bytes nulos y espacios para comparar contra el nombre recibido por FUSE.

    def encontrarEntrada(self,nombre):
        for entrada in self.entradas:
            if entrada.nombre_archivo.strip('\x00').strip() == nombre:
                return entrada
        return None

    #Lee el contenido de un archivo guardado dentro de FiUnamFS.
    #Primero localiza su entrada y después calcula el desplazamiento usando el cluster inicial.
    
    def leerEntrada(self,nombre):
        entrada = self.encontrarEntrada(nombre)
        if entrada != None:
            offset_entrada = entrada.cluster_incial * self.superbloque.tam_cluster
            with open(self.ruta_img, 'rb') as img:
                img.seek(offset_entrada)
                datos = img.read(entrada.tam_archivo)
                return datos
        else:
            return None

    #Escribe un archivo nuevo en FiUnamFS.
    #La operación valida duplicados, busca espacio contiguo, escribe los datos y registra la entrada.
    #El lock evita que dos operaciones modifiquen la imagen al mismo tiempo.
    
    def escribirEntrada(self, nombre, datos):

        with self.lock:

            if self.encontrarEntrada(nombre) is not None:
                print(f"Ya existe un archivo con el nombre '{nombre}'")
                return False
        
            clusters = (len(datos) + self.superbloque.tam_cluster - 1) // self.superbloque.tam_cluster
            cluster_incio = self.encontrarEspacio(clusters)
            if cluster_incio is None:
                print(f"No se encontró suficiente espacio en disco")
                return False

            else: 
                with open(self.ruta_img, 'r+b') as img:
                    img.seek(cluster_incio * self.superbloque.tam_cluster)
                    img.write(datos)
            
            entrada_libre = None
            for entrada in self.entradas:
                if entrada.tipo_archivo == ARCHIVO_VACIO:
                    entrada_libre = entrada
                    break
                
            if entrada_libre is None:
                print(f"No hay entradas libres en el directorio")
                return False
            
            entrada_libre.crearNuevo(nombre, len(datos), cluster_incio)
            with self.condicion:
                self.operaciones.append("sync")
                self.condicion.notify()
            return True

    #Busca el siguiente espacio disponible para guardar un archivo.
    #El método trabaja con asignación contigua, por lo que regresa el cluster inicial disponible.


    def encontrarEspacio(self, clusters_necesarios):
        ocupados = []
        for entrada in self.entradas:
            if entrada.tipo_archivo != ARCHIVO_VACIO and entrada.tam_archivo > 0:
                n_clusters = (entrada.tam_archivo + self.superbloque.tam_cluster - 1) // self.superbloque.tam_cluster
                ocupados.append(entrada.cluster_incial + n_clusters)

        if not ocupados:
            return self.superbloque.desp_datos // self.superbloque.tam_cluster
        
        siguiente = max(ocupados)
        
        if siguiente + clusters_necesarios > self.superbloque.num_clusters_tot:
            return None
        
        return siguiente
    
    #Elimina una entrada del directorio y solicita la sincronización del directorio en disco.
    #La eliminación es lógica: la entrada se marca como libre para que pueda reutilizarse.

    def eliminarEntrada(self,nombre):
        with self.lock:
            entrada = self.encontrarEntrada(nombre)
            if entrada != None:
                entrada.eliminar()
                with self.condicion:
                    self.operaciones.append("sync")
                    self.condicion.notify()
            else:
                print(f"No se encontró la entrada")

    #Reescribe el directorio completo en la imagen.
    #Se usa después de crear, modificar o eliminar entradas para mantener persistentes los cambios.
    
    def actualizarDisco(self):
        with self.lock:
            with open(self.ruta_img, 'r+b') as img:
                img.seek(self.superbloque.desp_dir)
                salida = bytearray()
                for entrada in self.entradas:
                    salida.extend(entrada.pasarBytes())
                salida = salida[:self.superbloque.tam_dir].ljust(self.superbloque.tam_dir, b'\x00')
                img.write(salida)

  
    #Sobrescribe el contenido de un archivo existente.
    #Esta función se usa cuando FUSE recibe una escritura sobre un archivo ya creado.

    def sobrescribirEntrada(self, nombre, datos):
        with self.lock:
            entrada = self.encontrarEntrada(nombre)
            if entrada is None:
                return False
            with open(self.ruta_img, 'r+b') as img:
                offset = entrada.cluster_incial * self.superbloque.tam_cluster
                img.seek(offset)
                img.write(datos)
            entrada.tam_archivo = len(datos)
            with self.condicion:
                self.operaciones.append("sync")
                self.condicion.notify()
            return True

    #Hilo encargado de esperar operaciones pendientes de sincronización.
    #Cuando recibe una operación "sync", actualiza el directorio de la imagen en segundo plano.
    def hiloEscritura(self):

        while True:

            with self.condicion:

                while not self.operaciones:
                    self.condicion.wait()

                operacion = self.operaciones.pop(0)

            if operacion == "sync":
                self.actualizarDisco()
