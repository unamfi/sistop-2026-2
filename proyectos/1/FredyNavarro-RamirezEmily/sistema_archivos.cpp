/*
Implementación de operaciones de FiUnamFS
Autores: Navarro Carbajal Fredy Emiliano, Ramírez Terán Emily
Descripción: Implementa las funciones para la manipulación
del sistema de archivos virtual. Utiliza fstream para realizar
operaciones de lectura y escritura binaria mediante desplazamientos 
(seek) sobre la estructura del disco (.img).
 */
#include "sistema_archivos.h"
#include "estructuras.h"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <ctime>

using namespace std;

/*
 Valida la integridad del disco leyendo el superbloque en el cluster 0.
 Utiliza limpieza de buffers para manejar caracteres de padding/nulos.
*/
bool validar_superbloque(){
    ifstream disco(RUTA_DISCO, ios::binary);
    if(!disco.is_open()){
        cerr << "[Error] No se pudo abrir " << RUTA_DISCO << "\n";
        return false;
    }

    Superbloque sb;
    disco.read(reinterpret_cast<char*>(&sb), sizeof(Superbloque));
    disco.close();
    //Limpieza de metadatos 
    string nombre(sb.nombre_fs, 9);
    string version(sb.version, 5);
    
    //Limpieza quita tanto nulos como espacios en blanco al final
    size_t fin_nom = nombre.find_last_not_of(" \x00");
    if(fin_nom != string::npos) nombre.erase(fin_nom + 1);
    else nombre.clear();

    size_t fin_ver = version.find_last_not_of(" \x00");
    if(fin_ver != string::npos) version.erase(fin_ver + 1);
    else version.clear();

    //Validación mediante búsqueda de subcadena usando find
    if(nombre.find("FiUnamFS") == string::npos || version.find("24-2")){
        cerr << "[Fatal] Archivo corrupto o versión incorrecta.\n";
        return false;
    }

    cout << "[FS] Disco validado. Cluster: " << sb.tamano_cluster << " bytes.\n";
    return true;
}

/*
 Itera sobre la tabla de directorios (cluster 1) y filtra entradas activas.
*/
void listar_directorio(){
    ifstream disco(RUTA_DISCO, ios::binary);
    if(!disco.is_open()){
        cerr << "[Error] No se pudo abrir " << RUTA_DISCO << "\n";
        return;
    }

    cout << "\n--- Contenido de FiUnamFS ---\n";
    cout << "Nombre\t\tTamaño(B)\tCluster\tFecha Creación\n";
    cout << "--------------------------------------------------------------\n";

    disco.seekg(1 * TAMANO_CLUSTER); //Saltamos al cluster 1

    for(int i = 0; i < ENTRADAS_POR_DIRECTORIO; ++i){
        EntradaDirectorio entrada;
        disco.read(reinterpret_cast<char*>(&entrada), sizeof(EntradaDirectorio));
        //Solo archivos activos (tipo '-')
        if(entrada.tipo == '-'){
            string nombre(entrada.nombre, 15);
            string fecha(entrada.fecha_creacion, 14);
            
            size_t fin_nombre = nombre.find_last_not_of(" \x00");
            if(fin_nombre != string::npos) nombre.erase(fin_nombre + 1);
            else nombre.clear();

            if(nombre != "###############" && !nombre.empty()){
                cout << nombre << "\t" 
                     << entrada.tamano << "\t\t" 
                     << entrada.cluster_inicial << "\t"
                     << fecha << "\n";
            }
        }
    }
    
    disco.close();
    cout << "--------------------------------------------------------------\n";
}

/*
 Lee los bytes del cluster de datos y los escribe en un archivo local.
*/
void copiar_desde_fs(const string& archivo_origen, const string& archivo_destino){
    ifstream disco(RUTA_DISCO, ios::binary);
    if(!disco.is_open()) return;
    
    //Búsqueda del archivo en la tabla de directorio
    disco.seekg(1 * TAMANO_CLUSTER);
    bool encontrado = false;
    EntradaDirectorio archivo_info;

    for(int i = 0; i < ENTRADAS_POR_DIRECTORIO; ++i){
        disco.read(reinterpret_cast<char*>(&archivo_info), sizeof(EntradaDirectorio));
        
        if(archivo_info.tipo == '-'){
            string nombre(archivo_info.nombre, 15);
            size_t fin_nombre = nombre.find_last_not_of(" \x00");
            if(fin_nombre != string::npos) nombre.erase(fin_nombre + 1);
            else nombre.clear();

            if(nombre.find(archivo_origen) != string::npos){
                encontrado = true;
                break;
            }
        }
    }

    if(!encontrado){
        cout << "[Error] El archivo '" << archivo_origen << "' no existe en FiUnamFS.\n";
        disco.close();
        return;
    }
    
    cout << "[FS] Extrayendo '" << archivo_origen << "' (" << archivo_info.tamano << " bytes)...\n";
    //Lectura de datos desde la posición de cluster inicial
    disco.seekg(archivo_info.cluster_inicial * TAMANO_CLUSTER);
    vector<char> buffer(archivo_info.tamano);
    disco.read(buffer.data(), archivo_info.tamano);
    disco.close();

    //Persistencia local
    ofstream salida(archivo_destino, ios::binary);
    if(!salida.is_open()){
        cerr << "[Error] No se pudo crear el archivo local '" << archivo_destino << "'\n";
        return;
    }
    
    salida.write(buffer.data(), archivo_info.tamano);
    salida.close();
    cout << "[FS] Archivo guardado exitosamente como '" << archivo_destino << "'\n";
}

/*
 Borrado lógico, modifica el metadato en la tabla sin necesidad de sobreescribir los datos.
*/
void eliminar_archivo(const string& archivo_borrar){
    fstream disco(RUTA_DISCO, ios::in | ios::out | ios::binary);
    if(!disco.is_open()){
        cerr << "[Error] No se pudo abrir " << RUTA_DISCO << "\n";
        return;
    }

    disco.seekg(1 * TAMANO_CLUSTER);
    bool encontrado = false;
    EntradaDirectorio entrada;

    for(int i = 0; i < ENTRADAS_POR_DIRECTORIO; ++i){
        long posicion_actual = disco.tellg(); 
        disco.read(reinterpret_cast<char*>(&entrada), sizeof(EntradaDirectorio));
        
        if(entrada.tipo == '-'){
            string nombre(entrada.nombre, 15);
            size_t fin_nombre = nombre.find_last_not_of(" \x00");
            if(fin_nombre != string::npos) nombre.erase(fin_nombre + 1);
            else nombre.clear();

            if(nombre.find(archivo_borrar) != string::npos){
                encontrado = true;
                
                disco.seekp(posicion_actual);
                
                char tipo_borrado = '/';
                string nombre_borrado = "###############"; 
                
                disco.write(&tipo_borrado, 1);
                disco.write(nombre_borrado.c_str(), 15);
                
                cout << "[FS] Archivo '" << archivo_borrar << "' eliminado lógicamente.\n";
                break;
            }
        }
    }

    if(!encontrado){
        cout << "[Error] El archivo '" << archivo_borrar << "' no existe en FiUnamFS.\n";
    }
    
    disco.close();
}

string obtener_fecha_actual(){
    time_t t = time(nullptr);
    tm* now = localtime(&t);
    char buffer[15];
    strftime(buffer, sizeof(buffer), "%Y%m%d%H%M%S", now);
    return string(buffer);
}

/*
Inserción, algoritmo de asignación contigua para gestión de espacio libre.
*/
void copiar_hacia_fs(const string& archivo_local, const string& nombre_en_fs){
    //Lectura del archivo local para calcular requisitos de espacio
    ifstream entrada(archivo_local, ios::binary | ios::ate);
    if(!entrada.is_open()){
        cout << "[Error] No se encuentra el archivo local '" << archivo_local << "'\n";
        return;
    }
    uint32_t tamano_archivo = entrada.tellg();
    entrada.seekg(0);

    fstream disco(RUTA_DISCO, ios::in | ios::out | ios::binary);
    if(!disco.is_open()) return;

    Superbloque sb;
    disco.read(reinterpret_cast<char*>(&sb), sizeof(Superbloque));
    //Calculo de clusters requeridos para el archivo
    uint32_t clusters_necesarios = (tamano_archivo + sb.tamano_cluster - 1) / sb.tamano_cluster;
    if(clusters_necesarios == 0) clusters_necesarios = 1;

    disco.seekg(1 * TAMANO_CLUSTER);
    //Mapa de bits para identificar clusters ocupados 
    vector<bool> mapa_clusters(sb.clusters_totales, false);
    for(uint32_t i = 0; i < 1 + sb.clusters_directorio; i++) mapa_clusters[i] = true;

    int indice_entrada_libre = -1;
    long pos_entrada_libre = -1;
    //Asignación contigua, busca el primer segmento contiguo
    for(int i = 0; i < ENTRADAS_POR_DIRECTORIO; ++i){
        long pos_actual = disco.tellg();
        EntradaDirectorio dir;
        disco.read(reinterpret_cast<char*>(&dir), sizeof(EntradaDirectorio));

        if(dir.tipo == '-' && dir.nombre[0] != '#'){
            uint32_t cl_ocupados = (dir.tamano + sb.tamano_cluster - 1) / sb.tamano_cluster;
            if(cl_ocupados == 0) cl_ocupados = 1;
            for(uint32_t j = 0; j < cl_ocupados; j++){
                if(dir.cluster_inicial + j < sb.clusters_totales)
                    mapa_clusters[dir.cluster_inicial + j] = true;
            }
        }else if((dir.tipo == '/' || dir.tipo == '\0' || dir.nombre[0] == '#') && pos_entrada_libre == -1) {
            pos_entrada_libre = pos_actual;
            indice_entrada_libre = i;
        }
    }

    if(pos_entrada_libre == -1){
        cout << "[Error] El directorio de FiUnamFS está lleno.\n";
        disco.close();
        return;
    }

    uint32_t cluster_inicial_libre = 0;
    uint32_t contiguos = 0;
    for(uint32_t i = 1 + sb.clusters_directorio; i < sb.clusters_totales; i++){
        if(!mapa_clusters[i]){
            if(contiguos == 0) cluster_inicial_libre = i;
            contiguos++;
            if(contiguos == clusters_necesarios) break;
        }else{
            contiguos = 0; 
        }
    }

    if(contiguos < clusters_necesarios){
        cout << "[Error] Espacio contiguo insuficiente. Necesita " << clusters_necesarios << " clusters.\n";
        disco.close();
        return;
    }

    cout << "[FS] Copiando '" << archivo_local << "' (" << tamano_archivo << " B) al cluster " << cluster_inicial_libre << "...\n";
    disco.seekp(cluster_inicial_libre * sb.tamano_cluster);
    vector<char> buffer(tamano_archivo);
    entrada.read(buffer.data(), tamano_archivo);
    disco.write(buffer.data(), tamano_archivo);
    entrada.close();

    disco.seekp(pos_entrada_libre);
    EntradaDirectorio nueva_entrada = {};
    nueva_entrada.tipo = '-';
    
    string nombre_limpio = nombre_en_fs.substr(0, 15);
    for(int i = 0; i < 15; i++){
        if(i < nombre_limpio.length()) nueva_entrada.nombre[i] = nombre_limpio[i];
        else nueva_entrada.nombre[i] = ' ';
    }
    
    nueva_entrada.tamano = tamano_archivo;
    nueva_entrada.cluster_inicial = cluster_inicial_libre;
    
    string fecha = obtener_fecha_actual();
    for(int i = 0; i < 14; i++){
        nueva_entrada.fecha_creacion[i] = fecha[i];
        nueva_entrada.fecha_modificacion[i] = fecha[i];
    }

    disco.write(reinterpret_cast<char*>(&nueva_entrada), sizeof(EntradaDirectorio));
    disco.close();

    cout << "[FS] Archivo '" << nombre_en_fs << "' guardado exitosamente.\n";
}
