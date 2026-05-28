"""
logica principal de sincronizacion con hilos en FiUnamFS

aqui definimos una cola de estados y un hilos el cual recibe mensajes
sobre el avance de las operaciones realizadas sobre la imagen
"""
import queue
import threading

"""
clase que administra los mecanismos de sincronizacion para FiUnamFS
"""
class Sincronizacion:
    def __init__(self):
        self.bloqueo_disco = threading.RLock()
        self.cola_estados = queue.Queue()
        self.hilo_estados = threading.Thread(target=self.procesar_estados, daemon=True)
        self.activo = False
    
    """
    inicia el hilo que procesa los estados
    """
    def iniciar(self):
        self.activo = True
        self.hilo_estados.start()
    
    """
    envia un mensaje de estado al hilo que los procesa
    """
    def notificar(self, mensaje):
        self.cola_estados.put(mensaje)
    
    """
    procesa los mensajes enviador por las operaciones realizadas
    """
    def procesar_estados(self):
        while True:
            mensaje = self.cola_estados.get()
            
            if mensaje is None:
                self.cola_estados.task_done()
                break
            
            print(f"[estado] {mensaje}")
            self.cola_estados.task_done()
    
    """
    para el uso del hilo de estados de forma ordenada
    """
    def detener(self):
        self.cola_estados.join()
        self.cola_estados.put(None)
        self.hilo_estados.join()
        self.activo = False
