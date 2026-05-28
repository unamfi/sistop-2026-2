/*
Autores: Navarro Carbajal Fredy Emiliano, Ramírez Terán Emily
Descripción: Define la capa de abstracción para la manipulación del disco
virtual. Contiene las constantes de diseño del sistema (clusters,
entradas de directorio) y la firma de los métodos encargados de la persistencia de datos.
 */

#ifndef SISTEMA_ARCHIVOS_H
#define SISTEMA_ARCHIVOS_H

#include <string>
//Constantes del sistema de archivos, define la ruta del archivo
const std::string RUTA_DISCO = "fiunamfs.img";
const int TAMANO_CLUSTER = 2048; //4 sectores de 512 bytes, tamaño del cluster
const int ENTRADAS_POR_DIRECTORIO = (8 * TAMANO_CLUSTER) / 64; //256 entradas máximas

//Verifica la firma y versión del superbloque para garantizar integridad.
bool validar_superbloque();
//Itera sobre la tabla de directorios e imprime el metadato de archivos activos.
void listar_directorio(); 
//Realiza la lectura binaria de un archivo en el FS y lo recrea en el sistema local.
void copiar_desde_fs(const std::string& archivo_origen, const std::string& archivo_destino);
//Implementa el borrado lógico, marca el archivo como disponible sin limpiar los datos.
void eliminar_archivo(const std::string& archivo_borrar);
//Implementa el algoritmo de asignación contigua, busca clusters libres para escribir datos 
//de un archivo local hacia el sistema virtual.
void copiar_hacia_fs(const std::string& archivo_local, const std::string& nombre_en_fs);
#endif
