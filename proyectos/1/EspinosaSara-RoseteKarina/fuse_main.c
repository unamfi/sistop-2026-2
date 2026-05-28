#ifdef __linux__
#define FUSE_USE_VERSION 35

#include <fuse3/fuse.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

#include "fiunamfs.h"

// Mantiene una instancia compartida de el sistema montado
typedef struct{
    FiUnamFS fs;
}FuseState;


// Recupera el estado global de FUSE
static FuseState *state(void){

    return (FuseState*)
    fuse_get_context()->private_data;
}


// Quita la diagonal inicial para trabajar solo con nombres
static const char *clean_path(
const char *path){

    if(path[0]=='/')
        return path+1;

    return path;
}


// Obtiene atributos para archivos o carpetas
static int fi_getattr(
const char *path,
struct stat *st,
struct fuse_file_info *fi){

    (void)fi;

    memset(
    st,
    0,
    sizeof(struct stat));

    // La raíz se trata como directorio
    if(strcmp(path,"/")==0){

        st->st_mode=
        S_IFDIR|0755;
        st->st_nlink=2;
        return 0;
    }

    const char *name=
    clean_path(path);

    DirEntry e;

    if(fs_get_entry_by_name(
        &state()->fs,
        name,
        &e)!=0){

        return -ENOENT;
    }

    st->st_mode=
    S_IFREG|0644;
    st->st_nlink=1;

    st->st_size=
    e.size;

    st->st_blksize=
    state()->fs.cluster_size;

    return 0;
}


// Llena el contenido que aparecerá con ls
static int fi_readdir(
const char *path,
void *buf,
fuse_fill_dir_t filler,
off_t offset,
struct fuse_file_info *fi,
enum fuse_readdir_flags flags){

    (void)offset;
    (void)fi;
    (void)flags;

    if(strcmp(path,"/")!=0)
        return -ENOENT;

    filler(
    buf,
    ".",
    NULL,
    0,
    0);

    filler(
    buf,
    "..",
    NULL,
    0,
    0);

    int total=
    fs_count_entries(
    &state()->fs);

    for(int i=0;i<total;i++){

        DirEntry e;

        if(fs_get_entry_by_index(
            &state()->fs,
            i,
            &e)!=0)

            return -EIO;

        if(e.type==
        TYPE_FILE &&
        e.name[0]!='\0'){

            filler(
            buf,
            e.name,
            NULL,
            0,
            0);
        }
    }

    return 0;
}


// Verifica que el archivo exista antes de abrirlo
static int fi_open(
const char *path,
struct fuse_file_info *fi){

    (void)fi;

    const char *name=
    clean_path(path);

    DirEntry e;

    if(fs_get_entry_by_name(
        &state()->fs,
        name,
        &e)!=0)

        return -ENOENT;

    return 0;
}


// Lee datos del archivo solicitado
static int fi_read(
const char *path,
char *buf,
size_t size,
off_t offset,
struct fuse_file_info *fi){

    (void)fi;

    const char *name=
    clean_path(path);

    int r=
    fs_read_file(
    &state()->fs,
    name,
    buf,
    size,
    offset);

    if(r<0)
        return -EIO;

    return r;
}


// Crea un nuevo archivo vacío
static int fi_create(
const char *path,
mode_t mode,
struct fuse_file_info *fi){

    (void)mode;
    (void)fi;

    const char *name=
    clean_path(path);

    if(strchr(name,'/')!=NULL
    | strlen(name)==0)

        return -EINVAL;

    if(!fs_valid_name(name))
        return -ENAMETOOLONG;

    int r=
    fs_create_empty_file(
    &state()->fs,
    name);

    if(r==-3)
        return -EEXIST;

    if(r==-4 || r==-5)
        return -ENOSPC;

    if(r!=0)
        return -EIO;

    return 0;
}


// Guarda datos nuevos dentro del archivo
static int fi_write(
const char *path,
const char *buf,
size_t size,
off_t offset,
struct fuse_file_info *fi){

    (void)fi;

    const char *name=
    clean_path(path);

    int r=
    fs_write_file(
    &state()->fs,
    name,
    buf,
    size,
    offset);

    if(r==-2)
        return -ENOSPC;

    if(r<0)
        return -EIO;

    return r;
}


// Ajusta el tamaño del archivo
static int fi_truncate(
const char *path,
off_t size,
struct fuse_file_info *fi){

    (void)fi;

    if(size<0 ||
    size>UINT32_MAX)

        return -EINVAL;

    const char *name=
    clean_path(path);

    int r=
    fs_truncate_file(
    &state()->fs,
    name,
    (uint32_t)size);

    if(r==-2)
        return -ENOSPC;

    if(r!=0)
        return -EIO;

    return 0;
}


// Elimina una entrada del directorio
static int fi_unlink(
const char *path){

    const char *name=
    clean_path(path);

    if(fs_delete(
        &state()->fs,
        name)!=0)

        return -ENOENT;

    return 0;
}


// Configura algunos parámetros al iniciar
static void *fi_init(
struct fuse_conn_info *conn,
struct fuse_config *cfg){

    (void)conn;

    cfg->kernel_cache=0;

    return state();
}


// Libera recursos al desmontar
static void fi_destroy(
void *private_data){

    FuseState *s=
    (FuseState*)
    private_data;

    if(s)
        fs_close(
        &s->fs);
}


// Relaciona operaciones FUSE con funciones reales
static const struct fuse_operations fi_ops={

    .init=fi_init,
    .destroy=fi_destroy,
    .getattr=fi_getattr,
    .readdir=fi_readdir,
    .open=fi_open,
    .read=fi_read,
    .create=fi_create,
    .write=fi_write,
    .truncate=fi_truncate,
    .unlink=fi_unlink
};


int main(
int argc,
char *argv[]){

    // Se necesita imagen y punto de montaje
    if(argc<3){

        fprintf(
        stderr,
        "Uso: %s <FiUnamFS.img> <punto_montaje>\n",
        argv[0]);

        return 1;
    }

    FuseState *s=
    calloc(
    1,
    sizeof(FuseState));

    if(!s){

        fprintf(
        stderr,
        "No hubo memoria\n");

        return 1;
    }

    if(fs_open(
        &s->fs,
        argv[1])!=0){

        free(s);

        return 1;
    }

    // FUSE recibe argumentos sin la imagen
    int fuse_argc=
    argc-1;

    char **fuse_argv=
    calloc(
    fuse_argc,
    sizeof(char*));

    if(!fuse_argv){

        fs_close(
        &s->fs);

        free(s);

        return 1;
    }

    fuse_argv[0]=argv[0];

    for(int i=2;i<argc;i++)
        fuse_argv[i-1]=argv[i];

    int result=
    fuse_main(
    fuse_argc,
    fuse_argv,
    &fi_ops,
    s);

    free(fuse_argv);
    free(s);

    return result;
}
#endif
