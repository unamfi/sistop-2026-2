from fiunamfs import FiUnamFS
import threading

# Arquitectura de hilos (Condition + Monitor):
#   - Hilo principal: parsea argumentos y ejecuta la operación pedida.
#   - Hilo monitor:   duerme en condition.wait() y despierta tras cada
#                     operación de escritura para verificar el estado del disco.

class Monitor:
    # Monitor es un hilo en segundo plano que observa el estado del disco tras cada
    # operación de escritura (paste / delete), forma parte de nuestro patrón
    # que busca implementar concurrencia.

    # Mecanismo de sincronización: threading.Condition
    
    # El hilo principal manda llamar a monitor.notificar(op) después de cada
    # escritura. Esto adquiere el Condition, actualiza la última
    # operación registrada y llama a condition.notify(), despertando
    # al hilo monitor.

    # Mientras tanto, el monitor duerme en condition.wait() entre notificaciones, 
    # sin consumir CPU. Al despertar, lee el estado del disco y emite
    # advertencias si es que detecta condiciones anómalas (espacio bajo, disco
    # lleno, etc).

    # Porcentaje mínimo de espacio libre antes de emitir advertencia
    UMBRAL_CRITICO = 10

    def __init__(self, fs: FiUnamFS):
        self._fs        = fs
        self._condition = threading.Condition() # Timbre para despertar 
        self._activo    = True
        self._hay_trabajo = False   # flag que persiste entre notificaciones
        self._ultima_op = None # Un espacio para guardar qué fue lo último 
        # que ocurrió (por ejemplo, "paste", "delete" o "list")
        self._hilo      = threading.Thread(
            target=self._ciclo, # Cuando el hilo arranque, ejecutará el método _ciclo
            name="monitor-fs", # Nombre que le damos al hilo
            daemon=False, # Si tuvieramos daemon TRUE, el programa se cerraría abruptamente en cuanto el
            # hilo principal terminara. Matando el monitor a la mitad de se ejcución.
        )

    def iniciar(self):
        # Arrancamos el hilo monitor.
        self._hilo.start()

    def detener(self):
        # Señala al monitor que debe terminar y espera a que salga.
        with self._condition:
            self._activo = False
            self._condition.notify_all()   # despierta al monitor para que pueda salir
        self._hilo.join()

    def notificar(self, operacion: str):
        # Despierta al monitor para que verifique el disco.
        # Debe llamarse desde el hilo principal tras toda operación de escritura.

        # Args:
            # operacion: Nombre de la operación que provocó el cambio ('paste' o 'delete').
        with self._condition: # Con with adquirimos el "candado"
            self._ultima_op = operacion
            self._hay_trabajo = True
            self._condition.notify()

    # Comienza el ciclo interno del monitor

    def _ciclo(self):
        with self._condition:
            while True:
                # Modificamos la espera: despertamos si hay trabajo ó si se apaga el monitor
                self._condition.wait_for(
                    lambda: self._hay_trabajo or not self._activo
                )

                # Prioridad: Si hay trabajo pendiente, lo procesamos sin importar 
                # que nos hayan pedido detenernos simultáneamente.
                if self._hay_trabajo:
                    self._hay_trabajo = False
                    try:
                        self._verificar()
                    except Exception as e:
                        print(f"[monitor] Error al verificar el disco: {e}")
                
                # Una vez procesado el trabajo pendiente, validamos si debemos salir
                if not self._activo:
                    break

    def _verificar(self):
        # Leemos el estado del disco mostrando un diagnóstico cada que se realice alguna inserción o 
        # eliminaación. En caso de que se detecte algún error, se mostrará una advertencia.
        estado = self._fs.estado_disco()

        total=estado['clusters_totales']
        libres=estado['clusters_libres']
        porcentaje=(libres / total * 100) if total>0 else 0.0

        print(f"\n[monitor] '{self._ultima_op}' completado — "
              f"{estado['num_archivos']} archivo(s), "
              f"{libres}/{total} clusters libres ({porcentaje:.1f}%)")

        if porcentaje < self.UMBRAL_CRITICO:
            print(f"[monitor] Espacio bajo: quedan solo {libres} clusters disponibles.")

        if libres == 0:
            print(f"[monitor] Disco lleno — la próxima escritura fallará.")

