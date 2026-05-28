#include "fiunamfs.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INPUT_SIZE 512

//Evita que ambos hilos escriban en el mismo tiempo
pthread_mutex_t console_mutex;

typedef enum{
    CMD_LIST,
    CMD_COPY_OUT,
    CMD_COPY_IN,
    CMD_DELETE,
    CMD_EXIT
}CommandType;


// Cada petición del usuario se guarda aquí
typedef struct CommandNode{

    CommandType type;
    char arg1[256];
    char arg2[256];

    struct CommandNode *next;

}CommandNode;


// Cola compartida entre el hilo principal y el trabajador
typedef struct{

    CommandNode *head;
    CommandNode *tail;
    int closed;
    pthread_mutex_t mutex;
    pthread_cond_t available;

}CommandQueue;

typedef struct{

    FiUnamFS *fs;
    CommandQueue *queue;

}WorkerArgs;


//Inicializa la cola y los mecanismos de sincronización
static void queue_init(CommandQueue *q){

    q->head=NULL;
    q->tail=NULL;
    q->closed=0;

    pthread_mutex_init(&q->mutex,NULL);
    pthread_cond_init(&q->available,NULL);
}


//Libera memoria usada por la cola
static void queue_destroy(CommandQueue *q){

    CommandNode *current=q->head;
    while(current){
        CommandNode *next=current->next;
        free(current);
        current=next;
    }

    pthread_mutex_destroy(&q->mutex);
    pthread_cond_destroy(&q->available);
}


//Agrega nuevas tareas para el trabajador
static void queue_push(CommandQueue *q,
const CommandNode *cmd){

    CommandNode *node=
    malloc(sizeof(CommandNode));

    if(!node){
        printf("Error memoria\n");
        return;
    }

    *node=*cmd;
    node->next=NULL;
    pthread_mutex_lock(&q->mutex);
    if(q->tail)
        q->tail->next=node;
    else
        q->head=node;
    q->tail=node;
    pthread_cond_signal(&q->available);
    pthread_mutex_unlock(&q->mutex);
}


// Espera hasta que exista una tarea pendiente
static int queue_pop(CommandQueue *q,
CommandNode *out){

    pthread_mutex_lock(&q->mutex);
    while(!q->head && !q->closed){
        pthread_cond_wait(
            &q->available,
            &q->mutex);
    }

    if(!q->head && q->closed){
        pthread_mutex_unlock(&q->mutex);
        return 0;
    }

    CommandNode *node=q->head;

    q->head=node->next;
    if(!q->head)
        q->tail=NULL;
    *out=*node;
    free(node);
    pthread_mutex_unlock(&q->mutex);
    return 1;
}


//Despierta al trabajador y cierra la cola
static void queue_close(CommandQueue *q){
    pthread_mutex_lock(&q->mutex);
    q->closed=1;

    pthread_cond_broadcast(
        &q->available);
    pthread_mutex_unlock(&q->mutex);
}


// El trabajador hace operaciones mientras el menú sigue disponible
static void *worker_thread(void *data){
    WorkerArgs *args=
    (WorkerArgs*)data;
    CommandNode cmd;

    while(queue_pop(args->queue,&cmd)){
        pthread_mutex_lock(
            &console_mutex);
        switch(cmd.type){
        case CMD_LIST:
            fs_list(args->fs);
            break;

        case CMD_COPY_OUT:

            fs_copy_from_fs(
                args->fs,
                cmd.arg1,
                cmd.arg2);
            break;

        case CMD_COPY_IN:

            fs_copy_to_fs(
                args->fs,
                cmd.arg1,
                cmd.arg2);
            break;


        case CMD_DELETE:

            fs_delete(
                args->fs,
                cmd.arg1);

            break;


        case CMD_EXIT:
            queue_close(
                args->queue);
            break;
        }

        pthread_mutex_unlock(
            &console_mutex);
    }

    return NULL;
}

int main(int argc,
char *argv[]){
// El programa necesita recibir el archivo img
    if(argc<2){

        printf(
        "Uso: %s archivo.img\n",
        argv[0]);

        return 1;
    }

    FiUnamFS fs;

    if(fs_open(
        &fs,
        argv[1])!=0){

        return 1;
    }

    CommandQueue queue;

    queue_init(&queue);

    pthread_mutex_init(
        &console_mutex,
        NULL);

    WorkerArgs args=
    {.fs=&fs,
     .queue=&queue};

    pthread_t worker;

    if(pthread_create(
        &worker,
        NULL,
        worker_thread,
        &args)!=0){

        printf(
        "Error creando hilo\n");
        return 1;
    }

    printf(
    "\n=== FiUnamFS ===\n");

    printf(
    "Trabajando sobre: %s\n",
    argv[1]);

    while(1){
        int opcion;
        CommandNode cmd;
        memset(
            &cmd,
            0,
            sizeof(cmd));
        pthread_mutex_lock(
            &console_mutex);

        printf(
        "\n========= MENU =========\n");
        printf(
        "1. Listar archivos\n");
        printf(
        "2. Copiar FiUnamFS -> PC\n");
        printf(
        "3. Copiar PC -> FiUnamFS\n");
        printf(
        "4. Eliminar archivo\n");
        printf(
        "5. Salir\n");
        printf(
        "\nOpcion: ");
        pthread_mutex_unlock(
            &console_mutex);
        scanf("%d",&opcion);
        getchar();
        switch(opcion){

        case 1:
            cmd.type=CMD_LIST;
            break;


        case 2:

            cmd.type=CMD_COPY_OUT;

            printf(
            "\nNombre archivo dentro de FiUnamFS: ");

            fgets(
                cmd.arg1,
                256,
                stdin);

            cmd.arg1[
            strcspn(
            cmd.arg1,
            "\n")]=0;

            printf(
            "Carpeta destino (Enter = actual): ");

            fgets(
                cmd.arg2,
                256,
                stdin);

            cmd.arg2[
            strcspn(
            cmd.arg2,
            "\n")]=0;

            break;


        case 3:

            cmd.type=CMD_COPY_IN;
            printf(
            "\nRuta del archivo local\n");

            printf(
            "(Debe ser un archivo, no una carpeta): ");

            fgets(
                cmd.arg1,
                256,
                stdin);

            cmd.arg1[
            strcspn(
            cmd.arg1,
            "\n")]=0;

            break;

        case 4:

            cmd.type=CMD_DELETE;

            printf(
            "\nArchivo a eliminar: ");

            fgets(
                cmd.arg1,
                256,
                stdin);

            cmd.arg1[
            strcspn(
            cmd.arg1,
            "\n")]=0;

            break;

        case 5:

            cmd.type=CMD_EXIT;
            break;
        default:

            printf(
            "\nOpcion invalida\n");

            continue;
        }
        queue_push(
            &queue,
            &cmd);
        if(cmd.type==
            CMD_EXIT){

            break;
        }
    }
    // Espera a que termine el trabajador antes de cerrar
    pthread_join(
        worker,
        NULL);

    queue_destroy(
        &queue);
    pthread_mutex_destroy(
        &console_mutex);
    fs_close(
        &fs);
    printf(
    "\nPrograma finalizado\n");

    return 0;
}
