import sys
import argparse
from fuse import FUSE
from worker import DiskWorker
from fiunamfs import FiUnamFS

def main():

    parser = argparse.ArgumentParser(description="FiUnamFS - Micro sistema de archivos multihilos")
    parser.add_argument("mount_point", help="Directorio vacío donde se montará FiUnamFS")
    parser.add_argument("image_file", help="Archivo de imagen del disco (ej. fiunamfs.img)")
    args = parser.parse_args()

    # iniciar el hilo Worker (Consumidor de I/O)
    worker = DiskWorker(args.image_file)
    worker.start()

    # iniciar la capa FUSE (Productor)
    try:
        print(f"Montando imagen '{args.image_file}' en el directorio '{args.mount_point}'...")
        fuse_ops = FiUnamFS(worker)
        # nothreads=True porque nosotros manejamos nuestros propios hilos (FUSE principal + Worker)
        FUSE(fuse_ops, args.mount_point, nothreads=True, foreground=True)
    except KeyboardInterrupt:
        # Se captura Ctrl+C para salir 
        pass
    except Exception as e:
        print(f"Error al iniciar FUSE: {e}")
    finally:
        print("\nDesmontando sistema de archivos y cerrando worker...")
        worker.stop()
        worker.join()

if __name__ == '__main__':
    main()

