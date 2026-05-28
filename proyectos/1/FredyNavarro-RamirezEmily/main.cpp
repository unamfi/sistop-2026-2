/*
Proyecto 1: Sistema de Archivos FiUnamFS
Autores: Navarro Carbajal Fredy Emiliano, Ramírez Terán Emily
Asignatura: Sistemas Operativos
Facultad de Ingeniería, UNAM
 
Descripción: Archivo principal que implementa la interfaz de usuario (Shell)
y el motor de procesamiento concurrente. Utiliza el patrón de diseño 
Productor-Consumidor para sincronizar la lectura de comandos del usuario
con la ejecución de operaciones de I/O en el sistema de archivos virtual.
*/
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <string>
#include <sstream>
#include <vector>
#include "sistema_archivos.h"

using namespace std;

/*
Estructura para encapsular los comandos ingresados por el usuario.
Actúa como el producto en nuestro modelo Productor-Consumidor.
*/
struct Tarea{
    string operacion;
    string arg1; 
    string arg2; 
};

//Variables globales para sincronización de hilos
queue<Tarea> cola_tareas; //Cola compartida de instrucciones
mutex mtx_cola;           //Candado para garantizar exclusión mutua en la cola  
condition_variable cv;    //Sincronizador para evitar espera activa 
bool apagar_sistema = false; //Bandera de control para el apagado seguro 

/*
 Función del hilo consumidor
 Se encarga de procesar las tareas encoladas y ejecutar las operaciones
 de bajo nivel sobre el archivo virtual (.img).
 */
void motor_archivos(){
    //Verificación de seguridad
    if(!validar_superbloque()){
        cout << "Apagando motor por seguridad\n";
        return;
    }

    while(true){
        unique_lock<mutex> lock(mtx_cola);
        //cv.wait suspende el hilo (evita consumo excesivo) hasta que
        //la cola tenga tareas o se reciba la señal de apagado.
        cv.wait(lock, []{ return !cola_tareas.empty() || apagar_sistema; });

        //Condición de salida, si hay señal de apagado y ya no hay tareas pendientes
        if(apagar_sistema && cola_tareas.empty()) break; 
        
        //Extraer la tarea de la zona crítica
        Tarea tarea = cola_tareas.front();
        cola_tareas.pop();
        //Liberar el candado antes de ejecutar la operación.
        lock.unlock(); 

        //Enrutador de comandos actualizado
        if(tarea.operacion == "ls"){
            listar_directorio();
        }else if(tarea.operacion == "cp_out"){
            if(tarea.arg1.empty() || tarea.arg2.empty()){
                cout << "[Uso] cp_out <archivo_en_fs> <nombre_local>\n";
            }else{
                copiar_desde_fs(tarea.arg1, tarea.arg2);
            }
        }else if(tarea.operacion == "rm"){
            if(tarea.arg1.empty()){
                cout << "[Uso] rm <archivo_en_fs>\n";
            }else{
                eliminar_archivo(tarea.arg1);
            }
        }else if(tarea.operacion == "cp_in"){
            if(tarea.arg1.empty() || tarea.arg2.empty()){
                cout << "[Uso] cp_in <archivo_local> <nombre_en_fs>\n";
            }else{
                copiar_hacia_fs(tarea.arg1, tarea.arg2);
            }
        }else{
            cout << "\n[Motor] Comando desconocido.\n";
        }
        
        //Restablece el prompt después de que el hilo termina su operación
        cout << "FiUnamFS> ";
        cout.flush();
    }
}

/*
 Función del Hilo Productor 
 Captura la entrada del usuario y la inyecta en la cola de tareas.
 */
int main(){
    //Lanzar el hilo consumidor en segundo plano
    thread hilo_fs(motor_archivos);
    cout << "Iniciando FiUnamFS\n";
    //Retardo para dar tiempo a que el motor valide el superbloque
    this_thread::sleep_for(chrono::milliseconds(100));

    while(true){
        cout << "FiUnamFS> ";
        string linea;
        //Capturar toda la línea ingresada para evitar bloqueos por espacios
        if(!getline(cin, linea)) break; 
        if(linea.empty()) continue;

        //Parseo del comando 
        istringstream stream(linea);
        string comando;
        stream >> comando;

        vector<string> args;
        string arg;
        while(stream >> arg){
            args.push_back(arg);
        }

        //Manejo de apagado del sistema
        if(comando == "exit"){
            lock_guard<mutex> lock(mtx_cola);
            apagar_sistema = true; 
            cv.notify_one();
            break;
        } 
        
        //Empaqueta la instrucción en la estructura
        Tarea nueva_tarea;
        nueva_tarea.operacion = comando;
        if(args.size() > 0) nueva_tarea.arg1 = args[0];
        if(args.size() > 1) nueva_tarea.arg2 = args[1];
        //Insertar la nueva tarea en la cola compartida
        {
            lock_guard<mutex> lock(mtx_cola);
            cola_tareas.push(nueva_tarea);
        }
        //Notifica al hilo consumidor que hay una nueva tarea lista
        cv.notify_one(); 
        this_thread::sleep_for(chrono::milliseconds(50));
    }

    hilo_fs.join();
    return 0;
}
