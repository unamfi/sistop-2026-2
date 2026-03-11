#Programita para un minishell, en python
#Autores: BrenaVíctor - CruzLizbeth
#Tarea1

#importación de bibliotecas
import os
import signal
import sys
import shlex

#Manejador de la señal SIGCHLD
#Recolecta procesos hijos terminados

def sigchld_handler(signum,frame):
	
	try:
		while True:
			pid, status = os.waitpid(-1, os.WNOHANG)
			#-1 significa cualquier hijo
			#WNOHANG evita el bloqueo
		
			if pid <= 0:
				break
			print(f"\n[minishell] hijo {pid} terminado")
			print("minishell> ", end="", flush=True)

	except ChildProcessError:
		pass

#Se define la función principal del mini shell
def main():
	#Ignorar Ctrl+C en el chell
	signal.signal(signal.SIGINT, signal.SIG_IGN)

	#Manejar terminación de hijos
	signal.signal(signal.SIGCHLD, sigchld_handler)
	#se cambia la linea anterior, ya que al ser entorno windows
	#el módulo signal no tiene SIGCHLD, y al compilar, sale como error
	#el cambio es el siguiente:
	#if hasattr(signal,"SIGCHLD"):
		#signal.signal(signal.SIGCHLD, sigchld_handler)
	#ya no se cambia nada, se ejecuto el progma en entorno linux
	#maquina virtual ubuntu onworks.net y corrio bien.
	
	while True:
		try:
			#Se muestra el prompt
			command_line = input("minishell>")
		except EOFError:
			print()
			break

		#Separar comando y argumentos
		args = shlex.split(command_line)

		if not command_line.strip():
			continue

		#Comando interno exit
		if args[0] == "exit":
			print("Saliendo del minishell...")
			sys.exit(0)
		try:

			#Crear proceso hijo
			pid = os.fork()

			if pid == 0:

				#inicia proceso hijo

				#Restaurar comportamiento Ctrl+C
				signal.signal(signal.SIGINT,signal.SIG_DFL)

				try:
					os.execvp(args[0],args)
				except FileNotFoundError:
					print(f"{args[0]}: comando no encontrado")
				os._exit(1)
			else:
				#inicia proceso padre
				#el padre no espera y SIGCHLD se encarga 
				pass

		except OSError as e:
			print("Error al crear proceso:", e)

if __name__ == "__main__":
	main ()
		
