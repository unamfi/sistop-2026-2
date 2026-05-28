import os
import sys
from P_sistop2026_2 import FiUnamFS

"""
Módulo FUSE (Filesystem in Userspace - Simulado)
Autores: Bello Sánchez Santiago Arath y López Romero David Baruc

Este script actúa como el controlador de interfaz de línea de comandos (CLI).
Implementa un ciclo REPL (Read-Eval-Print Loop) continuo que captura la entrada
estándar del usuario, la limpia y la segmenta en tokens. Actúa como una capa 
de abstracción, traduciendo comandos POSIX estándar (ls, cp, rm) en llamadas 
a los métodos internos del objeto FiUnamFS, aislando así la lógica del sistema 
de archivos de la interacción con el usuario.
"""

def iniciar_consola(ruta_imagen):
    try:
        print(f"Montando sistema de archivos desde: {ruta_imagen}")
        fs = FiUnamFS(ruta_imagen)
        print("\n¡Bienvenido a FiUnamFS!")
        print("Comandos disponibles: ls, cp, rm, exit\n")
        
        # Ciclo principal de control de eventos
        while True:
      
            entrada = input("FiUnamFS $ ").strip().split()
            
            if not entrada:
                continue
                
            comando = entrada[0].lower()
            
            if comando == 'exit' or comando == 'quit':
                print("Desmontando sistema y saliendo... ¡Adiós!")
                break
                
            elif comando == 'ls':
                fs.mapear_directorio()
                print("\n--- Contenido del directorio ---")
                if not fs.lista_archivos:
                    print("(Directorio vacío)")
                else:
                    for archivo in fs.lista_archivos:
                        print(f"- {archivo.name} ({archivo.size} bytes)")
                print("--------------------------------\n")
                
            elif comando == 'rm':
                if len(entrada) < 2:
                    print("Uso correcto: rm <nombre_del_archivo_en_FiUnamFS>")
                    continue
                nombre_archivo = entrada[1]
                fs._eliminarArchivo(nombre_archivo)
                
            elif comando == 'cp':
                if len(entrada) < 3:
                    print("Uso correcto:")
                    print("  Para copiar a tu equipo:  cp <archivo_FiUnamFS> <ruta_en_tu_equipo>")
                    print("  Para copiar a FiUnamFS: cp <ruta_en_tu_Mac> <archivo_nuevo_en_FiUnamFS>")
                    continue
                
                origen = entrada[1]
                destino = entrada[2]

                archivo_interno = next((f for f in fs.lista_archivos if f.name == origen), None)
                
                if archivo_interno:
                    if os.path.isdir(destino) or destino == '.':
                        if destino == '.': destino = os.getcwd()
                        print(f"Copiando '{origen}' hacia tu computadora en '{destino}'...")
                        fs.copia_TO_MyPC(destino, archivo_interno)
                    else:
                        print("Error: El destino en tu equipo debe ser una carpeta válida.")
                
                elif os.path.isfile(origen):
                    print(f"Copiando '{origen}' desde tu computadora hacia FiUnamFS...")
                    fs.copia_TO_FiUnamFS(origen)
                
                else:
                    print(f"Error: No se encontró el archivo '{origen}' ni en FiUnamFS ni en tu computadora.")
                    
            else:
                print(f"Comando no reconocido: {comando}")
                print("Usa: ls, cp, rm, o exit")

    except Exception as e:
        print(f"Error crítico: {e}")

if __name__ == "__main__":
    # Captura dinámica de parámetros desde el entorno de ejecución
    if len(sys.argv) != 2:
        print("Uso correcto: python FUSE.py <ruta_sistemaArchivos>")
    else:
        ruta_img = sys.argv[1]
        iniciar_consola(ruta_img)