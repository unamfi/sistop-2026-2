/*

 Proyecto Sistemas Operativos, Facultad de Ingeniería UNAM
 Versiones del sistema de archivos soportadas: 24-2, 26-2

 fiunamfs.c — Implementación FUSE del micro sistema de archivos FiUnamFS

 ---- Autores ----
 - Monroy Tapia Jesús Alejandro
 - Ponce de León Reyes Bruno

 Compilación: Uso del comando "make" para emplear el Makefile ubicado en el mismo directorio
 Para más información acerca del uso consultar la documentación: "README.md"

*/

#define FUSE_USE_VERSION 31
#include <fuse.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <assert.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/stat.h>

// ----------- Constantes del sistema de archivos -----------

#define FS_NAME             "FiUnamFS"
static const char *FS_VERSIONES_VALIDAS[] = { "24-2", "26-2", NULL };

/* Prefijo fijo del nombre del FS en el superbloque */
#define FS_VERSION_PREFIJO "  -2"   /* las versiones comparten sufijo */
#define SECTOR_SIZE         512
#define SECTORS_PER_CLUSTER 4
#define CLUSTER_SIZE        (SECTOR_SIZE * SECTORS_PER_CLUSTER)  /* 2 048 bytes */
#define DISK_SIZE           (1440 * 1024)                         /* 1 440 KiB  */
#define TOTAL_CLUSTERS      (DISK_SIZE / CLUSTER_SIZE)            /* 720        */

// ----------- Superbloque (Cluster 0) -----------
#define SB_NAME_OFF      5
#define SB_NAME_LEN      9
#define SB_VER_OFF       14
#define SB_VER_LEN       5
#define SB_LABEL_OFF     20
#define SB_LABEL_LEN     16
#define SB_CLSIZE_OFF    40
#define SB_DIRSIZE_OFF   50
#define SB_TOTALCL_OFF   60

// ----------- Directorio -----------
#define DIR_START_CLUSTER       1
#define DIR_CLUSTERS            8
#define DIR_ENTRY_SIZE          64
#define DIR_ENTRIES_PER_CLUSTER (CLUSTER_SIZE / DIR_ENTRY_SIZE)
#define MAX_DIR_ENTRIES         (DIR_CLUSTERS * DIR_ENTRIES_PER_CLUSTER)
#define NAME_LEN                15
#define TIMESTAMP_LEN           14

// ----------- Marcadores de entrada -----------
#define ENTRY_FILE    '-'   
#define ENTRY_EMPTY   '/'   
#define ENTRY_DELETED '#'   // Nombre "###############"

// ----------- Offsets dentro de cada entrada de directorio (64 bytes) -----------
#define DE_TYPE_OFF    0
#define DE_NAME_OFF    1
#define DE_SIZE_OFF    16   /* uint32_t little-endian */
#define DE_CLUSTER_OFF 20   /* uint32_t little-endian */
#define DE_CTIME_OFF   24
#define DE_MTIME_OFF   40

/*
 * - Estructuras -
*/


struct __attribute__((packed)) fiunamfs_entry {
	char     type;           /* '-' archivo válido, '/' libre               */
	char     name[16];       /* nombre + '\0' (15 caracteres útiles)        */
	uint32_t size;           /* tamaño en bytes, little-endian              */
	uint32_t start_cluster;  /* número del primer cluster de datos          */
	char     ctime[15];      /* fecha-hora de creación: AAAAMMDDHHMMSS'\0'  */
	char     mtime[15];      /* fecha-hora de modificación: AAAAMMDDHHMMSS'\0' */
	char     reserved[12];   /* padding para completar los 64 bytes         */
};


typedef struct {
	int      fd;                                    
	uint32_t cluster_size;
	uint32_t dir_clusters;
	uint32_t total_clusters;
	char     label[SB_LABEL_LEN + 1];

	struct fiunamfs_entry dir[MAX_DIR_ENTRIES];     
	int      dir_count;                            

	
	int            dir_dirty;   
	pthread_cond_t sync_cond;   
	pthread_t      sync_thread;
	int            shut_down;   
} FiUnamFS;

static FiUnamFS g_fs;


static pthread_mutex_t fs_mutex   = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t sync_mutex = PTHREAD_MUTEX_INITIALIZER;

// ------------------- Utilidades para bajo nivel -------------------

// Leer los bytes del disco en el offset indicado con la función pread
static int leer_disco(void *buf, size_t count, off_t offset)
{
	if (pread(g_fs.fd, buf, count, offset) != (ssize_t)count) {
		perror("leer_disco");
		return -EIO;
	}
	return 0;
}

// Escribir bytes al disco en el offset indicado con la función pwrite
static int escribir_disco(const void *buf, size_t count, off_t offset)
{
	if (pwrite(g_fs.fd, buf, count, offset) != (ssize_t)count) {
		perror("escribir_disco");
		return -EIO;
	}
	return 0;
}

// Devuelve el offset en bytes del inicio del cluster n
static inline off_t cluster_offset(uint32_t n)
{
	return (off_t)n * CLUSTER_SIZE;
}


// Leer valor uint32_t con formato Little Endian de buf[off]
static inline uint32_t leer_le32(const uint8_t *buf, int off)
{
	return (uint32_t)buf[off]
	     | ((uint32_t)buf[off+1] <<  8)
	     | ((uint32_t)buf[off+2] << 16)
	     | ((uint32_t)buf[off+3] << 24);
}

// Escribir valor como uint32_t con formato Little Endian en buf[off]
static inline void escribir_le32(uint8_t *buf, int off, uint32_t val)
{
	buf[off]   = (uint8_t)( val        & 0xff);
	buf[off+1] = (uint8_t)((val >>  8) & 0xff);
	buf[off+2] = (uint8_t)((val >> 16) & 0xff);
	buf[off+3] = (uint8_t)((val >> 24) & 0xff);
}


// Generar cadena con el tiempo actual — Formato: AAAAMMDDHHMMSS
static void now_timestamp(char *buf)
{
	time_t t = time(NULL);
	struct tm *tm = localtime(&t);
	strftime(buf, TIMESTAMP_LEN + 1, "%Y%m%d%H%M%S", tm);
}

// Convertir cadena del timestamp a time_t (para struct stat)
static time_t parse_timestamp(const char *ts)
{
	if (!ts || strlen(ts) < 14) return 0;
	struct tm t = {0};
	char tmp[5];
	// Conversión considerando el diseño de struct tm en C (año desde 1900, mes 0-11)
	memcpy(tmp, ts,    4); tmp[4] = 0; t.tm_year = atoi(tmp) - 1900;
	memcpy(tmp, ts+4,  2); tmp[2] = 0; t.tm_mon  = atoi(tmp) - 1;
	memcpy(tmp, ts+6,  2); tmp[2] = 0; t.tm_mday = atoi(tmp);
	memcpy(tmp, ts+8,  2); tmp[2] = 0; t.tm_hour = atoi(tmp);
	memcpy(tmp, ts+10, 2); tmp[2] = 0; t.tm_min  = atoi(tmp);
	memcpy(tmp, ts+12, 2); tmp[2] = 0; t.tm_sec  = atoi(tmp);
	t.tm_isdst = -1;
	return mktime(&t); // Desde la época Unix
}


static void entrada_a_raw(const struct fiunamfs_entry *e, uint8_t *raw)
{
	memset(raw, 0, DIR_ENTRY_SIZE);
	raw[DE_TYPE_OFF] = (uint8_t)e->type;
	// Nombre: copiamos NAME_LEN bytes; el byte extra de name[16] queda fuera
	strncpy((char *)raw + DE_NAME_OFF, e->name, NAME_LEN);
	escribir_le32(raw, DE_SIZE_OFF,    e->size);
	escribir_le32(raw, DE_CLUSTER_OFF, e->start_cluster);
	strncpy((char *)raw + DE_CTIME_OFF, e->ctime, TIMESTAMP_LEN);
	strncpy((char *)raw + DE_MTIME_OFF, e->mtime, TIMESTAMP_LEN);
}


static void raw_a_entrada(const uint8_t *raw, struct fiunamfs_entry *e)
{
	e->type = (char)raw[DE_TYPE_OFF];

	memcpy(e->name, raw + DE_NAME_OFF, NAME_LEN);
	e->name[NAME_LEN] = '\0';

	for (int i = NAME_LEN - 1; i >= 0; i--) {
		if (e->name[i] == ' ' || e->name[i] == '\0') {
			e->name[i] = '\0';
		} else {
			break; 
		}
	}

	e->size          = leer_le32(raw, DE_SIZE_OFF);
	e->start_cluster = leer_le32(raw, DE_CLUSTER_OFF);

	memcpy(e->ctime, raw + DE_CTIME_OFF, TIMESTAMP_LEN);
	e->ctime[TIMESTAMP_LEN] = '\0';

	memcpy(e->mtime, raw + DE_MTIME_OFF, TIMESTAMP_LEN);
	e->mtime[TIMESTAMP_LEN] = '\0';
}


static int cargar_directorio(void)
{
	uint8_t raw[DIR_ENTRY_SIZE];
	g_fs.dir_count = 0;

	for (int cl = DIR_START_CLUSTER;
	     cl < DIR_START_CLUSTER + (int)g_fs.dir_clusters;
	     cl++)
	{
		for (int slot = 0; slot < (int)DIR_ENTRIES_PER_CLUSTER; slot++) {
			int idx = (cl - DIR_START_CLUSTER) * DIR_ENTRIES_PER_CLUSTER + slot;
			if (idx >= MAX_DIR_ENTRIES) break;

			off_t off = cluster_offset(cl) + (off_t)(slot * DIR_ENTRY_SIZE);
			if (leer_disco(raw, DIR_ENTRY_SIZE, off) != 0)
				return -EIO;

			raw_a_entrada(raw, &g_fs.dir[idx]);

			if (g_fs.dir[idx].type == ENTRY_FILE)
				g_fs.dir_count++;
		}
	}
	return 0;
}


static int volcar_directorio(void)
{
	uint8_t raw[DIR_ENTRY_SIZE];

	for (int cl = DIR_START_CLUSTER;
	     cl < DIR_START_CLUSTER + (int)g_fs.dir_clusters;
	     cl++)
	{
		for (int slot = 0; slot < (int)DIR_ENTRIES_PER_CLUSTER; slot++) {
			int idx = (cl - DIR_START_CLUSTER) * DIR_ENTRIES_PER_CLUSTER + slot;
			if (idx >= MAX_DIR_ENTRIES) break;

			entrada_a_raw(&g_fs.dir[idx], raw);
			off_t off = cluster_offset(cl) + (off_t)(slot * DIR_ENTRY_SIZE);
			if (escribir_disco(raw, DIR_ENTRY_SIZE, off) != 0)
				return -EIO;
		}
	}
	return 0;
}


static int find_entry(const char *name)
{
	for (int i = 0; i < MAX_DIR_ENTRIES; i++) {
		if (g_fs.dir[i].type == ENTRY_FILE &&
		    strncmp(g_fs.dir[i].name, name, NAME_LEN) == 0)
			return i;
	}
	return -1;
}


static int find_free_entry(void)
{
	for (int i = 0; i < MAX_DIR_ENTRIES; i++) {
		if (g_fs.dir[i].type != ENTRY_FILE)
			return i;
	}
	return -1;
}


static uint32_t alloc_clusters(uint32_t n)
{
	int used[TOTAL_CLUSTERS];
	memset(used, 0, sizeof(used));

	// Reservar superbloque + directorio
	uint32_t data_start = DIR_START_CLUSTER + g_fs.dir_clusters;
	for (uint32_t c = 0; c < data_start; c++)
		used[c] = 1;

	// Marcar clusters ocupados por cada archivo
	for (int i = 0; i < MAX_DIR_ENTRIES; i++) {
		if (g_fs.dir[i].type != ENTRY_FILE) continue;
		uint32_t cl  = g_fs.dir[i].start_cluster;
		uint32_t nb  = (g_fs.dir[i].size + CLUSTER_SIZE - 1) / CLUSTER_SIZE;
		for (uint32_t j = 0; j < nb && cl + j < TOTAL_CLUSTERS; j++)
			used[cl + j] = 1;
	}

	// Búsqueda lineal de n clusters contiguos libres
	for (uint32_t start = data_start;
	     start + n <= g_fs.total_clusters;
	     start++)
	{
		int ok = 1;
		for (uint32_t k = 0; k < n; k++) {
			if (used[start + k]) { ok = 0; break; }
		}
		if (ok) return start;
	}
	return 0; // Sin espacio suficiente
}


static void marcar_sucio(void)
{
	pthread_mutex_lock(&sync_mutex);
	g_fs.dir_dirty = 1;
	pthread_cond_signal(&g_fs.sync_cond);
	pthread_mutex_unlock(&sync_mutex);
}


static void *sync_thread_func(void *arg)
{
	(void)arg;

	pthread_mutex_lock(&sync_mutex);
	while (!g_fs.shut_down) {
		// Espera pasiva: libera sync_mutex y duerme hasta recibir señal
		while (!g_fs.dir_dirty && !g_fs.shut_down)
			pthread_cond_wait(&g_fs.sync_cond, &sync_mutex);

		if (!g_fs.dir_dirty) {
			// Despertó solo por shut_down
			pthread_mutex_unlock(&sync_mutex);
			break;
		}

		g_fs.dir_dirty = 0;                  // Consumir la bandera
		pthread_mutex_unlock(&sync_mutex);

		// Persistir el directorio bajo el mutex del sistema de archivos
		pthread_mutex_lock(&fs_mutex);
		volcar_directorio();
		pthread_mutex_unlock(&fs_mutex);

		pthread_mutex_lock(&sync_mutex);     // Retomar para la siguiente vuelta
	}
	return NULL;
}


static int fiunamfs_getattr(const char *path, struct stat *stbuf,
                             struct fuse_file_info *fi)
{
	(void)fi;
	memset(stbuf, 0, sizeof(struct stat));

	// Caso especial: raíz del sistema de archivos
	if (strcmp(path, "/") == 0) {
		stbuf->st_mode  = S_IFDIR | 0755;
		stbuf->st_nlink = 2;
		return 0;
	}

	const char *name = path + 1; // Salta la diagonal inicial

	pthread_mutex_lock(&fs_mutex);
	int idx = find_entry(name);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}
	struct fiunamfs_entry e = g_fs.dir[idx];
	pthread_mutex_unlock(&fs_mutex);

	stbuf->st_mode  = S_IFREG | 0644;
	stbuf->st_nlink = 1;
	stbuf->st_size  = (off_t)e.size;
	stbuf->st_atime = parse_timestamp(e.mtime);
	stbuf->st_mtime = parse_timestamp(e.mtime);
	stbuf->st_ctime = parse_timestamp(e.ctime);
	return 0;
}


static int fiunamfs_readdir(const char *path, void *buf,
                             fuse_fill_dir_t filler, off_t offset,
                             struct fuse_file_info *fi,
                             enum fuse_readdir_flags flags)
{
	(void)offset; (void)fi; (void)flags;

	if (strcmp(path, "/") != 0)
		return -ENOENT;

	filler(buf, ".",  NULL, 0, 0); // Directorio actual
	filler(buf, "..", NULL, 0, 0); // Directorio padre

	pthread_mutex_lock(&fs_mutex); // Adquirir mutex
	for (int i = 0; i < MAX_DIR_ENTRIES; i++) {
		if (g_fs.dir[i].type == ENTRY_FILE) {
			struct stat st = {0};
			st.st_mode  = S_IFREG | 0644;
			st.st_size  = (off_t)g_fs.dir[i].size;
			st.st_mtime = parse_timestamp(g_fs.dir[i].mtime);
			st.st_ctime = parse_timestamp(g_fs.dir[i].ctime);
			filler(buf, g_fs.dir[i].name, &st, 0, 0);
		}
	}
	pthread_mutex_unlock(&fs_mutex); // Liberar mutex
	return 0;
}


static int fiunamfs_open(const char *path, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&fs_mutex);
	int idx = find_entry(path + 1);
	pthread_mutex_unlock(&fs_mutex);
	return (idx < 0) ? -ENOENT : 0;
}


static int fiunamfs_read(const char *path, char *buf, size_t size,
                          off_t offset, struct fuse_file_info *fi)
{
	(void)fi;

	pthread_mutex_lock(&fs_mutex);

	int idx = find_entry(path + 1);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}

	struct fiunamfs_entry e = g_fs.dir[idx];

	// Offset pasado el fin del archivo — no hay bytes que retornar
	if (offset >= (off_t)e.size) {
		pthread_mutex_unlock(&fs_mutex);
		return 0;
	}

	// Recortar para no leer más allá del fin del archivo
	if (offset + (off_t)size > (off_t)e.size)
		size = (size_t)((off_t)e.size - offset);

	// Offset absoluto en la imagen: inicio del cluster + desplazamiento
	off_t disk_off = cluster_offset(e.start_cluster) + offset;
	int   ret      = leer_disco(buf, size, disk_off);

	pthread_mutex_unlock(&fs_mutex);

	return (ret == 0) ? (int)size : ret;
}


static int fiunamfs_create(const char *path, mode_t mode,
                            struct fuse_file_info *fi)
{
	(void)mode; (void)fi;
	const char *name = path + 1;

	if (strlen(name) > NAME_LEN)
		return -ENAMETOOLONG;

	pthread_mutex_lock(&fs_mutex);

	// El archivo no debe existir ya
	if (find_entry(name) >= 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -EEXIST;
	}

	// Buscar slot libre en el directorio
	int slot = find_free_entry();
	if (slot < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOSPC;
	}

	// Reservar al menos 1 cluster para el nuevo archivo
	uint32_t cl = alloc_clusters(1);
	if (cl == 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOSPC;
	}

	// Rellenar la nueva entrada de directorio
	struct fiunamfs_entry *e = &g_fs.dir[slot];
	e->type = ENTRY_FILE;
	memset(e->name, 0, sizeof(e->name));
	strncpy(e->name, name, NAME_LEN);
	e->size          = 0;
	e->start_cluster = cl;
	now_timestamp(e->ctime);
	now_timestamp(e->mtime);
	g_fs.dir_count++;

	pthread_mutex_unlock(&fs_mutex);
	marcar_sucio();
	return 0;
}


static int fiunamfs_truncate(const char *path, off_t newsize,
                              struct fuse_file_info *fi)
{
	(void)fi;
	const char *name = path + 1;

	pthread_mutex_lock(&fs_mutex);

	int idx = find_entry(name);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}

	struct fiunamfs_entry *e = &g_fs.dir[idx];

	
	uint32_t clusters_asignados =
	    (e->size > 0)
	        ? (e->size + CLUSTER_SIZE - 1) / CLUSTER_SIZE
	        : 1;  // create() siempre reserva al menos 1 cluster

	uint32_t clusters_necesarios =
	    (newsize > 0)
	        ? (uint32_t)((newsize + CLUSTER_SIZE - 1) / CLUSTER_SIZE)
	        : 1;

	// Si el nuevo tamaño requiere más clusters, reubicar el archivo.
	if (clusters_necesarios > clusters_asignados) {
		uint32_t nuevo_cl = alloc_clusters(clusters_necesarios);
		if (nuevo_cl == 0) {
			pthread_mutex_unlock(&fs_mutex);
			return -ENOSPC;
		}
		e->start_cluster = nuevo_cl;
	}

	e->size = (uint32_t)newsize;
	now_timestamp(e->mtime);

	pthread_mutex_unlock(&fs_mutex);
	marcar_sucio();
	return 0;
}


static int fiunamfs_write(const char *path, const char *buf, size_t size,
                           off_t offset, struct fuse_file_info *fi)
{
	(void)fi;

	pthread_mutex_lock(&fs_mutex);

	int idx = find_entry(path + 1);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}

	struct fiunamfs_entry *e = &g_fs.dir[idx];

	// Verificar que la escritura no supera el espacio asignado por truncate.
	uint32_t capacidad = e->start_cluster == 0 ? 0 :
	    ((e->size + CLUSTER_SIZE - 1) / CLUSTER_SIZE) * CLUSTER_SIZE;
	if (e->start_cluster != 0 && offset + (off_t)size > (off_t)capacidad) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOSPC;
	}

	
	off_t disk_off = cluster_offset(e->start_cluster) + offset;
	int   ret      = escribir_disco(buf, size, disk_off);

	if (ret == 0)
		now_timestamp(e->mtime); 

	pthread_mutex_unlock(&fs_mutex);

	if (ret == 0)
		marcar_sucio(); 

	return (ret == 0) ? (int)size : ret;
}


static int fiunamfs_unlink(const char *path)
{
	const char *name = path + 1;

	pthread_mutex_lock(&fs_mutex);

	int idx = find_entry(name);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}

	// Marcar la entrada como libre
	g_fs.dir[idx].type = ENTRY_EMPTY;
	// Rellenar el nombre con '#' — convención visual del formato FiUnamFS
	memset(g_fs.dir[idx].name, ENTRY_DELETED, NAME_LEN);
	g_fs.dir[idx].name[NAME_LEN] = '\0';
	g_fs.dir_count--;

	pthread_mutex_unlock(&fs_mutex);
	marcar_sucio(); 
	return 0;
}



static int fiunamfs_rename(const char *from, const char *to,
                            unsigned int flags)
{
	(void)flags;
	const char *nombre_viejo = from + 1;
	const char *nombre_nuevo = to   + 1;

	if (strlen(nombre_nuevo) > NAME_LEN)
		return -ENAMETOOLONG;

	pthread_mutex_lock(&fs_mutex);

	int idx = find_entry(nombre_viejo);
	if (idx < 0) {
		pthread_mutex_unlock(&fs_mutex);
		return -ENOENT;
	}

	// Si el destino ya existe, marcarlo como eliminado (semántica POSIX)
	int dst = find_entry(nombre_nuevo);
	if (dst >= 0) {
		g_fs.dir[dst].type = ENTRY_EMPTY;
		memset(g_fs.dir[dst].name, ENTRY_DELETED, NAME_LEN);
		g_fs.dir[dst].name[NAME_LEN] = '\0';
		g_fs.dir_count--;
	}

	// Escribir el nuevo nombre sobre la entrada existente
	memset(g_fs.dir[idx].name, 0, sizeof(g_fs.dir[idx].name));
	strncpy(g_fs.dir[idx].name, nombre_nuevo, NAME_LEN);
	now_timestamp(g_fs.dir[idx].mtime);

	pthread_mutex_unlock(&fs_mutex);
	marcar_sucio();
	return 0;
}



static int fiunamfs_statfs(const char *path, struct statvfs *stbuf)
{
	(void)path;
	memset(stbuf, 0, sizeof(struct statvfs));

	pthread_mutex_lock(&fs_mutex);

	uint32_t data_start    = DIR_START_CLUSTER + g_fs.dir_clusters;
	uint32_t data_clusters = g_fs.total_clusters - data_start;
	uint32_t usados        = 0;

	for (int i = 0; i < MAX_DIR_ENTRIES; i++) {
		if (g_fs.dir[i].type != ENTRY_FILE) continue;
		usados += (g_fs.dir[i].size + CLUSTER_SIZE - 1) / CLUSTER_SIZE;
	}

	pthread_mutex_unlock(&fs_mutex);

	stbuf->f_bsize   = CLUSTER_SIZE;        
	stbuf->f_frsize  = CLUSTER_SIZE;          
	stbuf->f_blocks  = data_clusters;         
	stbuf->f_bfree   = data_clusters - usados; 
	stbuf->f_bavail  = data_clusters - usados; 
	stbuf->f_namemax = NAME_LEN;              
	return 0;
}

static void *fiunamfs_init(struct fuse_conn_info *conn,
                            struct fuse_config *cfg)
{
	(void)conn;
	cfg->kernel_cache = 0; 
	return NULL;
}


static void fiunamfs_destroy(void *private_data)
{
	(void)private_data;

	// Señalar al hilo sync que debe terminar
	pthread_mutex_lock(&sync_mutex);
	g_fs.shut_down = 1;
	pthread_cond_signal(&g_fs.sync_cond);
	pthread_mutex_unlock(&sync_mutex);
	pthread_join(g_fs.sync_thread, NULL);

	// Escritura final de seguridad: asegura que no quede nada sin persistir
	pthread_mutex_lock(&fs_mutex);
	volcar_directorio();
	pthread_mutex_unlock(&fs_mutex);

	close(g_fs.fd);
}



static const struct fuse_operations fiunamfs_oper = {
	.init     = fiunamfs_init,
	.destroy  = fiunamfs_destroy,
	.getattr  = fiunamfs_getattr,
	.readdir  = fiunamfs_readdir,
	.open     = fiunamfs_open,
	.read     = fiunamfs_read,
	.create   = fiunamfs_create,
	.truncate = fiunamfs_truncate,
	.write    = fiunamfs_write,
	.unlink   = fiunamfs_unlink,   
	.rename   = fiunamfs_rename,   
	.statfs   = fiunamfs_statfs,   
};



// Muestra el uso correcto del comando al usuario
static void uso_FUSE(const char *prog)
{
	fprintf(stderr,
		"Uso: %s <imagen.img> <punto_de_montaje> [opciones_fuse]\n"
		"\n"
		"Opciones de FUSE:\n"
		"  -f              Ejecutar en primer plano\n"
		"  -d              Modo debug (implica -f)\n"
		"  -o allow_other  Permite acceso a otros usuarios\n",
		prog);
}

int main(int argc, char *argv[])
{
	// Verificar argumentos mínimos
	if (argc < 3) {
		uso_FUSE(argv[0]);
		return 1;
	}

	const char *img_path = argv[1];

	// 1. Abrir imagen del disco
	g_fs.fd = open(img_path, O_RDWR);
	if (g_fs.fd < 0) {
		perror(img_path);
		return 1;
	}

	// 2. Leer superbloque (cluster 0)
	uint8_t sb[CLUSTER_SIZE];
	if (leer_disco(sb, CLUSTER_SIZE, 0) != 0) {
		fprintf(stderr, "Error al leer el superbloque\n");
		close(g_fs.fd);
		return 1;
	}

	// Validar nombre del sistema de archivos
	char fs_name[SB_NAME_LEN + 1];
	memcpy(fs_name, sb + SB_NAME_OFF, SB_NAME_LEN);
	fs_name[SB_NAME_LEN] = '\0';
	if (strncmp(fs_name, FS_NAME, strlen(FS_NAME)) != 0) {
		fprintf(stderr,
			"Error: Este no es un volumen 'FiUnamFS' (Encontrado: '%s')\n",
			fs_name);
		close(g_fs.fd);
		return 1;
	}

	// Validar versión del sistema de archivos
	char fs_ver[SB_VER_LEN + 1];
	memcpy(fs_ver, sb + SB_VER_OFF, SB_VER_LEN);
	fs_ver[SB_VER_LEN] = '\0';
	{
		int version_ok = 0;
		for (int v = 0; FS_VERSIONES_VALIDAS[v] != NULL; v++) {
			if (strncmp(fs_ver, FS_VERSIONES_VALIDAS[v],
			            strlen(FS_VERSIONES_VALIDAS[v])) == 0) {
				version_ok = 1;
				break;
			}
		}
		if (!version_ok) {
			fprintf(stderr,
				"Error: Version '%s' no soportada\n"
				"       Versiones aceptadas: 24-2, 26-2\n",
				fs_ver);
			close(g_fs.fd);
			return 1;
		}
	}
	fprintf(stdout, " > Version detectada  : %s\n", fs_ver);

	// Leer parámetros del superbloque (formato little-endian)
	g_fs.cluster_size   = leer_le32(sb, SB_CLSIZE_OFF);
	g_fs.dir_clusters   = leer_le32(sb, SB_DIRSIZE_OFF);
	g_fs.total_clusters = leer_le32(sb, SB_TOTALCL_OFF);
	memcpy(g_fs.label, sb + SB_LABEL_OFF, SB_LABEL_LEN);
	g_fs.label[SB_LABEL_LEN] = '\0';

	// Mostrar características del sistema detectado
	fprintf(stdout,
		"FiUnamFS montando '%s'\n"
		" > Etiqueta           : %s\n"
		" > Tamanio del cluster: %u bytes\n"
		" > Clusters para Dir  : %u\n"
		" > Total de clusters  : %u\n",
		img_path, g_fs.label,
		g_fs.cluster_size, g_fs.dir_clusters, g_fs.total_clusters);

	// 3. Cargar directorio en memoria
	if (cargar_directorio() != 0) {
		fprintf(stderr, "Error al cargar directorio\n");
		close(g_fs.fd);
		return 1;
	}
	fprintf(stdout, " > Archivos encontrados: %d\n", g_fs.dir_count);

	// 4. Inicializar sincronización y lanzar hilo sync
	pthread_cond_init(&g_fs.sync_cond, NULL);
	g_fs.dir_dirty = 0;
	g_fs.shut_down = 0;
	if (pthread_create(&g_fs.sync_thread, NULL, sync_thread_func, NULL) != 0) {
		perror("pthread_create");
		close(g_fs.fd);
		return 1;
	}

	
	int    fuse_argc = argc - 1;
	char **fuse_argv = argv + 1;
	fuse_argv[0] = argv[0];

	return fuse_main(fuse_argc, fuse_argv, &fiunamfs_oper, NULL);
}