import os
import signal
import shlex
import sys


def manejador_sigchld(_signum, _frame):
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                # No hay más hijos que recolectar por ahora
                break
    except ChildProcessError:
        # No quedan procesos hijos
        pass


def configurar_señales():

    # El shell ignora Ctrl+C; los hijos restaurarán el comportamiento por omisión
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Instala el manejador para recolectar procesos hijos
    signal.signal(signal.SIGCHLD, manejador_sigchld)


def ejecutar_comando(args):

    pid = os.fork()

    if pid < 0:
        print("minishell: error al crear proceso (fork falló)", file=sys.stderr)
        return

    if pid == 0:
        # --- Proceso hijo ---
        # Restaura SIGINT al comportamiento por omisión (el hijo sí puede terminar con Ctrl+C)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        try:
            os.execvp(args[0], args)
        except FileNotFoundError:
            print(f"minishell: {args[0]}: comando no encontrado", file=sys.stderr)
        except PermissionError:
            print(f"minishell: {args[0]}: permiso denegado", file=sys.stderr)
        except Exception as e:
            print(f"minishell: {args[0]}: {e}", file=sys.stderr)

        os._exit(1)

    else:
        # --- Proceso padre ---
        # Espera a que el hijo termine antes de volver al prompt
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass


def main():
    configurar_señales()

    while True:
        try:
            # Muestra el directorio actual como parte del prompt
            cwd = os.getcwd()
            entrada = input(f"{cwd} $ ")
        except EOFError:
            # Ctrl+D: terminar limpiamente
            print("\nbye!")
            sys.exit(0)

        entrada = entrada.strip()
        if not entrada:
            continue

        try:
            args = shlex.split(entrada)
        except ValueError as e:
            print(f"minishell: error al parsear: {e}", file=sys.stderr)
            continue

        if args[0] == "exit":
            print("bye!")
            sys.exit(0)

        if args[0] == "cd":
            destino = args[1] if len(args) > 1 else os.path.expanduser("~")
            try:
                os.chdir(destino)
            except FileNotFoundError:
                print(f"minishell: cd: {destino}: no existe el directorio", file=sys.stderr)
            except NotADirectoryError:
                print(f"minishell: cd: {destino}: no es un directorio", file=sys.stderr)
            continue

        ejecutar_comando(args)


if __name__ == "__main__":
    main()
