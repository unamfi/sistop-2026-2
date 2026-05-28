#ifndef ESTRUCTURAS_H
#define ESTRUCTURAS_H

#include <cstdint>

#pragma pack(push, 1)

//Estructura del Cluster 0 (Superbloque)
struct Superbloque {
    char padding1[5];           
    char nombre_fs[9];          
    char version[5];            
    char padding2[1];           
    char etiqueta[16];          
    char padding3[4];           
    uint32_t tamano_cluster;    
    char padding4[6];           
    uint32_t clusters_directorio; 
    char padding5[6];           
    uint32_t clusters_totales;  
};

//Estructura de las entradas del directorio (64 bytes)
struct EntradaDirectorio {
    char tipo;                 
    char nombre[15];           
    uint32_t tamano;           
    uint32_t cluster_inicial;  
    char padding1[6];          
    char fecha_creacion[14];   
    char padding2[6];          
    char fecha_modificacion[14]; 
};

#pragma pack(pop)

#endif
