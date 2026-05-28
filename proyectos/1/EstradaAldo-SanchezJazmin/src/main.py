#!/usr/bin/env python3
"""
Inicio de proyecto FiUnamFS

En este punto aun no se monta FUSE, por lo que no modificamos la imagen "fiunamfs.img",
pero dejamos el ambiente preparado para montar FiUnamFS con FUSE.
"""
from pathlib import Path
import sys

from argumentos import crear_parser, validar_rutas
from fiunamfs import FiUnamFS
from sincronizacion import Sincronizacion
from sistema_fuse import SistemaFuse

def main():
    parser = crear_parser()
    args = parser.parse_args()
    
    ruta_imagen = Path(args.imagen).resolve()
    ruta_montaje = Path(args.montaje).resolve()
    
    if not validar_rutas(ruta_imagen, ruta_montaje):
        return 1
    
    sincronizacion = Sincronizacion()
    sincronizacion.iniciar()
    try:
        sistema = FiUnamFS(ruta_imagen, sincronizacion)
        
        if not sistema.validar_superbloque():
            return 1
        
        if args.listar:
            archivos = sistema.listar_archivos()
            
            print("\nConteido del directorio:")
            if not archivos:
                print("No hay archivos registrados")
            else:
                for archivo in archivos:
                    print(
                        f"- {archivo.nombre_archivo} | "
                        f"{archivo.tamano} | "
                        f"cluster inicial: {archivo.cluster_inicial} | "
                        f"fecha creacion: {archivo.fecha_creacion} | "
                        f"ultima modificacion: {archivo.fecha_modificacion}"
                    )
        elif args.leer:
            contenido = sistema.leer_archivo(args.leer)
            
            if contenido is None:
                return 1
            
            print(f"El contenido del archivo '{args.leer} es:'")
            print(contenido.decode("ascii", errors="replace"))
        elif args.copiar:
            ruta_destino = Path(args.destino).resolve()
            
            if not sistema.copiar_archivo(args.copiar, ruta_destino):
                return 1
        elif args.eliminar:
            if not sistema.eliminar_archivo(args.eliminar):
                return 1
        elif args.insertar:
            ruta_archivo_local = Path(args.insertar).resolve()
            
            if not sistema.insertar_archivo(ruta_archivo_local):
                return 1
        else:
            servidor = SistemaFuse(
                sistema,
                version="%prog",
                usage="FiUnamFS montado con FUSE",
                dash_s_do="setsingle"
            )
            
            servidor.parse(
                values=servidor,
                errex=1,
                args=[sys.argv[0], str(ruta_montaje)]
            )
            
            servidor.main()
        
        return 0
    finally:
        sincronizacion.detener()

if __name__ == "__main__":
    sys.exit(main())
