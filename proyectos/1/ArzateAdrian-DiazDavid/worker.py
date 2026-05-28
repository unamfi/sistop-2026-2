import threading
import queue

CLUSTER_SIZE = 2048  # Tamaño de un clúster en bytes (2KB)

class DiskWorker(threading.Thread):
    """
    Capa Consumidora: Se encarga de procesar las operaciones en tiempo real sobre 
    el archivo fiunamfs.img de manera segura y concurrente.
    """
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        self.task_queue = queue.Queue()
        self.daemon = True
        self.running = True

    def run(self):
        try:
            # Abrimos el archivo simulando el disco.
            # 'r+b' permite leer y escribir en el archivo binario sin truncarlo.
            with open(self.image_path, 'r+b') as disk:
                while self.running:
                    task = self.task_queue.get()
                    
                    # Un None en la cola para apagar el hilo
                    if task is None:
                        self.task_queue.task_done()
                        break
                    
                    self._process_task(disk, task)
                    self.task_queue.task_done()
                    
        except FileNotFoundError:
            print(f"Error: No se encontró el archivo de imagen '{self.image_path}'")
        except Exception as e:
            print(f"Error en el hilo de disco: {e}")

    def _process_task(self, disk, task):
        task_type = task.get('type')
        event = task.get('event')
        
        try:
            if task_type == 'TEST':
                pass
            #  leemos un cluster
            if task_type == 'READ_CLUSTER':
                cluster_id = task['cluster_id']
                disk.seek(cluster_id * CLUSTER_SIZE)
                task['result'] = disk.read(CLUSTER_SIZE)
            
            # sobreescribimos un cluster
            elif task_type == 'WRITE_CLUSTER':
                cluster_id = task['cluster_id']
                data = task['data']
                disk.seek(cluster_id * CLUSTER_SIZE)
                
                # Rellenar con ceros si los datos miden menos que un clúster
                if len(data) < CLUSTER_SIZE:
                    data = data.ljust(CLUSTER_SIZE, b'\x00')
                # Por si se intenta escribir más de un clúster se lanza el error
                elif len(data) > CLUSTER_SIZE:
                    raise ValueError("Se intentó escribir más de un clúster a la vez")
                    
                disk.write(data)
                task['result'] = True

            elif task_type == 'READ_BYTES':
                offset = task['offset']
                size = task['size']
                disk.seek(offset)
                task['result'] = disk.read(size)


            task['success'] = True
        except Exception as e:
            task['success'] = False
            task['error'] = e
        finally:
            # Despertamos al hilo FUSE (Productor) que estaba esperando
            if event:
                event.set()

    def _submit_sync(self, task):
        """
        Envía una tarea al Worker y bloquea hasta que termine.
        """
        event = threading.Event()
        task['event'] = event
        self.task_queue.put(task)
        event.wait()
        
        if not task.get('success', False):
            raise task.get('error', Exception("I/O desconocida. Error en Worker"))
            
        return task.get('result')

    def read_cluster(self, cluster_id):
        """
        Lee un clúster de 2048 bytes.
        """
        return self._submit_sync({'type': 'READ_CLUSTER', 'cluster_id': cluster_id})

    def write_cluster(self, cluster_id, data):
        """
        Escribe hasta 2048 bytes en el clúster indicado.
        """
        return self._submit_sync({'type': 'WRITE_CLUSTER', 'cluster_id': cluster_id, 'data': data})
        
    def read_bytes(self, offset, size):
        """
        Lee una cantidad exacta de bytes en una posición cruda.
        """
        return self._submit_sync({'type': 'READ_BYTES', 'offset': offset, 'size': size})

    def stop(self):
        self.running = False
        # Insertamos un None en la cola para destrabar el self.task_queue.get() bloqueante
        self.task_queue.put(None)
