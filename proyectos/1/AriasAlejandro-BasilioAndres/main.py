#!/usr/bin/env python3
import sys
import argparse

from fiunamfs import FiUnamFSDisk, FiUnamFS, FiUnamFSError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='main.py',
        description='FiUnamFS — sistema de archivos de asignación contigua',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'comandos disponibles:\n'
            '  -ls              Lista todos los archivos del directorio con nombre,\n'
            '                   tamaño en bytes, cluster de inicio y fecha de modificación.\n'
            '\n'
            '  -cp_out          Extrae un archivo del sistema FiUnamFS y lo guarda\n'
            '                   en el sistema operativo host.\n'
            '                   Ejemplo: python main.py disco.img -cp_out hola.txt ./hola.txt\n'
            '\n'
            '  -cp_in           Copia un archivo del host al sistema FiUnamFS.\n'
            '                   Si no hay espacio contiguo suficiente, sugiere ejecutar -defrag.\n'
            '                   Ejemplo: python main.py disco.img -cp_in ./foto.jpg foto.jpg\n'
            '\n'
            '  -rm              Elimina un archivo del directorio de FiUnamFS (borrado lógico).\n'
            '                   Los clusters que ocupaba quedan disponibles para reutilizarse.\n'
            '                   Ejemplo: python main.py disco.img -rm hola.txt\n'
            '\n'
            '  -defrag          Compacta el espacio libre moviendo todos los archivos\n'
            '                   al inicio de la zona de datos y cero-ando los clusters restantes.\n'
            '                   Útil antes de -cp_in cuando no hay bloques contiguos libres.\n'
            '\n'
            '  -mount           Monta el sistema de archivos como directorio del SO usando FUSE.\n'
            '                   Requiere tener instalado fusepy.\n'
            '                   Ejemplo: python main.py disco.img -mount /mnt/fiunam\n'
        ),
    )
    p.add_argument('imagen', metavar='IMG',
                   help='Ruta al archivo .img de FiUnamFS')

    ops = p.add_mutually_exclusive_group(required=True)
    ops.add_argument('-ls', action='store_true',
                     help='Listar archivos del directorio')
    ops.add_argument('-cp_out', nargs=2,
                     metavar=('NOMBRE', 'DESTINO'),
                     help='Extraer archivo de FiUnamFS al host')
    ops.add_argument('-cp_in', nargs=2,
                     metavar=('ORIGEN', 'NOMBRE'),
                     help='Copiar archivo del host a FiUnamFS')
    ops.add_argument('-rm', metavar='NOMBRE',
                     help='Eliminar archivo del sistema (borrado lógico)')
    ops.add_argument('-defrag', action='store_true',
                     help='Compactar espacio libre moviendo archivos al inicio')
    ops.add_argument('-mount', metavar='PUNTO',
                     help='Montar el sistema con FUSE en el punto indicado')
    return p


def main() -> None:
    print("FiUnamFS  |  Ejecuta  python main.py -h  para ver todos los comandos disponibles\n")
    parser = build_parser()
    args = parser.parse_args()

    try:
        with FiUnamFSDisk(args.imagen) as disk:
            fs = FiUnamFS(disk)

            if args.ls:
                fs.ls()
            elif args.cp_out:
                fs.cp_out(args.cp_out[0], args.cp_out[1])
            elif args.cp_in:
                fs.cp_in(args.cp_in[0], args.cp_in[1])
            elif args.rm:
                fs.rm(args.rm)
            elif args.defrag:
                fs.defrag()
            elif args.mount:
                from fiunamfs.fuse_ops import FiUnamFSFuse
                FiUnamFSFuse(fs).mount(args.mount)

    except FiUnamFSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == '__main__':
    main()
