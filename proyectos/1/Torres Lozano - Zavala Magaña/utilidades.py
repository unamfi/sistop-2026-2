# utilidades.py
# Funciones de presentación para la interfaz del programa.
#
# Usamos secuencias de escape ANSI para los colores y para limpiar la
# pantalla. Esto evita tener que llamar a 'cls' en Windows o 'clear'
# en Unix, que son comandos externos que generan llamadas al sistema
# innecesarias solo para limpiar una terminal.
#
# Las secuencias ANSI funcionan en Linux, macOS y Windows 10 o posterior.

# Formato de los códigos ANSI: \033[ + número + m
# \033 es el carácter ESC (código ASCII 27), que le indica a la terminal
# que lo que sigue es un comando de formato y no texto normal.
class Color:
    RESET    = "\033[0m"   # Volver al color que tenía la terminal
    NEGRITA  = "\033[1m"

    ROJO     = "\033[31m"
    VERDE    = "\033[32m"
    AMARILLO = "\033[33m"
    AZUL     = "\033[34m"
    CIAN     = "\033[36m"
    BLANCO   = "\033[37m"

    FONDO_AZUL   = "\033[44m"
    FONDO_OSCURO = "\033[40m"


def limpiar_pantalla() -> None:
    """
    Limpia la terminal usando secuencias ANSI, sin llamar a comandos externos.

    \033[2J → borra todo lo visible en la terminal
    \033[H  → mueve el cursor al inicio (fila 1, columna 1)
    """
    print("\033[2J\033[H", end="")


def imprimir_encabezado(titulo: str) -> None:
    """Muestra un encabezado con fondo azul y el título de la sección."""
    ancho = 50
    barra = "─" * ancho
    print(f"\n{Color.FONDO_AZUL}{Color.NEGRITA}  {'FiUnamFS':^{ancho}}  {Color.RESET}")
    print(f"{Color.AZUL}{barra}{Color.RESET}")
    print(f"{Color.CIAN}{Color.NEGRITA}  {titulo}{Color.RESET}\n")


def imprimir_exito(mensaje: str) -> None:
    """Mensaje de éxito en verde."""
    print(f"{Color.VERDE}{mensaje}{Color.RESET}")


def imprimir_error(mensaje: str) -> None:
    """Mensaje de error en rojo."""
    print(f"{Color.ROJO}{mensaje}{Color.RESET}")


def imprimir_info(mensaje: str) -> None:
    """Mensaje informativo en amarillo."""
    print(f"{Color.AMARILLO}{mensaje}{Color.RESET}")


def formatear_tamano(bytes_totales: int) -> str:
    """
    Convierte bytes a una unidad más legible.
    Por ejemplo: 31094 → '30.4 KB'
    """
    if bytes_totales < 1024:
        return f"{bytes_totales} B"
    elif bytes_totales < 1024 ** 2:
        return f"{bytes_totales / 1024:.1f} KB"
    else:
        return f"{bytes_totales / 1024 ** 2:.1f} MB"
