#include "fiunamfs.h"

#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

//FiUnamFS guarda varios enteros en little endian, por eso se leen byte por byte/
// Los enteros se reconstruyen byte por byte
static uint32_t read_u32_le(const unsigned char *b) {
    return ((uint32_t)b[0]) |
        ((uint32_t)b[1] << 8) |
        ((uint32_t)b[2] << 16) |
        ((uint32_t)b[3] << 24);
}

static void write_u32_le(unsigned char *b, uint32_t value) {
    b[0] = (unsigned char)(value & 0xFF);
    b[1] = (unsigned char)((value >> 8) & 0xFF);
    b[2] = (unsigned char)((value >> 16) & 0xFF);
    b[3] = (unsigned char)((value >> 24) & 0xFF);
}

//Copia cadenas del directorio quitando espacios de relleno al final
// Limpia espacios usados como relleno
static void trim_copy(char *dest, const unsigned char *src, size_t n) {
    size_t end = n;
    while (end > 0 && (src[end - 1] == ' ' || src[end - 1] == '\0')) {
        end--;
    }
    memcpy(dest, src, end);
    dest[end] = '\0';
}

// Valida nombres compatibles con el sistema
int fs_valid_name(const char *name) {
    size_t len = strlen(name);
    if (len == 0 || len > MAX_NAME_LEN) {
        return 0;
    }
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)name[i];
        if (c < 32 || c > 126 || c == '/' || c == '\\') {
            return 0;
        }
    }
    return 1;
}

// Obtiene solo el nombre ignorando la ruta
static void basename_simple(const char *path, char *out, size_t out_size) {
    const char *p1 = strrchr(path, '/');
    const char *p2 = strrchr(path, '\\');
    const char *base = path;
    if (p1 && p1 + 1 > base) base = p1 + 1;
    if (p2 && p2 + 1 > base) base = p2 + 1;
    snprintf(out, out_size, "%s", base);
}

// Genera una fecha con el formato usado por FiUnamFS
static void current_timestamp(char out[15]) {

    time_t now=time(NULL);
    struct tm *tm_info=localtime(&now);
    strftime(out,15,"%Y%m%d%H%M%S",tm_info);
    out[14]='\0';
}

static long cluster_offset(FiUnamFS *fs, uint32_t cluster) {
    return (long)cluster * (long)fs->cluster_size;
}

// Lee una entrada completa del directorio
static int read_entry_at(FiUnamFS *fs, int index, DirEntry *entry) {
    unsigned char raw[DIR_ENTRY_SIZE];
    long offset = fs->dir_start + (long)index * DIR_ENTRY_SIZE;

    if (fseek(fs->disk, offset, SEEK_SET) != 0) return -1;
    if (fread(raw, 1, DIR_ENTRY_SIZE, fs->disk) != DIR_ENTRY_SIZE) return -1;

    entry->type = (char)raw[0];
    trim_copy(entry->name, raw + 1, MAX_NAME_LEN);
    entry->size = read_u32_le(raw + 16);
    entry->start_cluster = read_u32_le(raw + 20);
    trim_copy(entry->created, raw + 30, 14);
    trim_copy(entry->modified, raw + 50, 14);
    entry->entry_offset = offset;
    return 0;
}

static int write_empty_entry(FiUnamFS *fs, long entry_offset) {
    unsigned char raw[DIR_ENTRY_SIZE];
    memset(raw, '#', sizeof(raw));
    raw[0] = TYPE_FREE;

    if (fseek(fs->disk, entry_offset, SEEK_SET) != 0) return -1;
    if (fwrite(raw, 1, DIR_ENTRY_SIZE, fs->disk) != DIR_ENTRY_SIZE) return -1;
    fflush(fs->disk);
    return 0;
}

static int write_file_entry(FiUnamFS *fs, long entry_offset, const char *name,
                            uint32_t size, uint32_t start_cluster) {
    unsigned char raw[DIR_ENTRY_SIZE];
    char stamp[15];

    memset(raw, ' ', sizeof(raw));
    raw[0] = TYPE_FILE;
    memcpy(raw + 1, name, strlen(name));
    write_u32_le(raw + 16, size);
    write_u32_le(raw + 20, start_cluster);

    current_timestamp(stamp);
    memcpy(raw + 30, stamp, 14);
    memcpy(raw + 50, stamp, 14);

    if (fseek(fs->disk, entry_offset, SEEK_SET) != 0) return -1;
    if (fwrite(raw, 1, DIR_ENTRY_SIZE, fs->disk) != DIR_ENTRY_SIZE) return -1;
    fflush(fs->disk);
    return 0;
}

static int max_entries(FiUnamFS *fs) {
    return (int)((fs->dir_clusters * fs->cluster_size) / DIR_ENTRY_SIZE);
}

// Busca un archivo recorriendo el directorio
static int find_entry(FiUnamFS *fs, const char *name, DirEntry *found) {
    int total = max_entries(fs);
    for (int i = 0; i < total; i++) {
        DirEntry e;
        if (read_entry_at(fs, i, &e) != 0) return -1;
        if (e.type == TYPE_FILE && strcmp(e.name, name) == 0) {
            if (found) *found = e;
            return i;
        }
    }
    return -1;
}

// Busca un espacio libre para guardar una entrada
static int find_free_entry(FiUnamFS *fs, long *entry_offset) {
    int total = max_entries(fs);
    for (int i = 0; i < total; i++) {
        DirEntry e;
        if (read_entry_at(fs, i, &e) != 0) return -1;
        if (e.type == TYPE_FREE || e.name[0] == '#') {
            *entry_offset = e.entry_offset;
            return 0;
        }
    }
    return -1;
}

static int clusters_needed(uint32_t bytes, uint32_t cluster_size) {
    if (bytes == 0) return 1;
    return (int)((bytes + cluster_size - 1) / cluster_size);
}

static int mark_used_clusters(FiUnamFS *fs, unsigned char *used, uint32_t cluster, int count) {
    if (cluster >= fs->total_clusters) return -1;
    for (int i = 0; i < count; i++) {
        uint32_t c = cluster + (uint32_t)i;
        if (c >= fs->total_clusters) return -1;
        used[c] = 1;
    }
    return 0;
}

// Busca bloques continuos para evitar fragmentación
static int find_contiguous_space(FiUnamFS *fs, int needed) {
    unsigned char *used = calloc(fs->total_clusters, 1);
    if (!used) return -1;

    /* El superbloque y el directorio no se pueden usar para datos. */
    for (uint32_t c = 0; c <= fs->dir_clusters && c < fs->total_clusters; c++) {
        used[c] = 1;
    }

    int total = max_entries(fs);
    for (int i = 0; i < total; i++) {
        DirEntry e;
        if (read_entry_at(fs, i, &e) != 0) {
            free(used);
            return -1;
        }
        if (e.type == TYPE_FILE) {
            int taken = clusters_needed(e.size, fs->cluster_size);
            if (mark_used_clusters(fs, used, e.start_cluster, taken) != 0) {
                free(used);
                return -1;
            }
        }
    }

    int run = 0;
    int start = -1;
    for (uint32_t c = fs->dir_clusters + 1; c < fs->total_clusters; c++) {
        if (!used[c]) {
            if (run == 0) start = (int)c;
            run++;
            if (run == needed) {
                free(used);
                return start;
            }
        } else {
            run = 0;
            start = -1;
        }
    }

    free(used);
    return -1;
}

// Carga y valida la información del sistema
int fs_open(FiUnamFS *fs, const char *disk_path) {
    unsigned char super[128];
    char magic[9];
    char version[6];

    memset(fs, 0, sizeof(*fs));
    snprintf(fs->path, sizeof(fs->path), "%s", disk_path);
    fs->disk = fopen(disk_path, "r+b");
    if (!fs->disk) {
        fprintf(stderr, "No se pudo abrir el disco '%s': %s\n", disk_path, strerror(errno));
        return -1;
    }

    if (fread(super, 1, sizeof(super), fs->disk) != sizeof(super)) {
        fprintf(stderr, "No se pudo leer el superbloque.\n");
        fclose(fs->disk);
        return -1;
    }

    memcpy(magic, super + 5, 8);
    magic[8] = '\0';
    memcpy(version, super + 14, 5);
    version[5] = '\0';

    if (strcmp(magic, MAGIC_EXPECTED) != 0) {
        fprintf(stderr, "El archivo no parece ser FiUnamFS. Firma encontrada: '%s'\n", magic);
        fclose(fs->disk);
        return -1;
    }
    if (strcmp(version, VERSION_EXPECTED) != 0) {
        fprintf(stderr, "Version no soportada: '%s'. Se esperaba '%s'.\n", version, VERSION_EXPECTED);
        fclose(fs->disk);
        return -1;
    }

    fs->cluster_size = read_u32_le(super + 40);
    fs->dir_clusters = read_u32_le(super + 50);
    fs->total_clusters = read_u32_le(super + 60);

    if (fs->cluster_size == 0 || fs->dir_clusters == 0 || fs->total_clusters == 0) {
        fprintf(stderr, "El superbloque tiene valores invalidos.\n");
        fclose(fs->disk);
        return -1;
    }

    fs->dir_start = cluster_offset(fs, 1);
    fs->data_start = cluster_offset(fs, fs->dir_clusters + 1);
    pthread_mutex_init(&fs->disk_lock, NULL);

    return 0;
}

void fs_close(FiUnamFS *fs) {
    if (fs->disk) fclose(fs->disk);
    pthread_mutex_destroy(&fs->disk_lock);
}

// Recorre y muestra los archivos existentes
int fs_list(FiUnamFS *fs) {
    pthread_mutex_lock(&fs->disk_lock);

    int total = max_entries(fs);
    int count = 0;

    printf("\nContenido de FiUnamFS:\n");
    printf("%-16s %-10s %-10s %-15s %-15s\n", "Nombre", "Tamano", "Cluster", "Creacion", "Modificacion");
    printf("-----------------------------------------------------------------------\n");

    for (int i = 0; i < total; i++) {
        DirEntry e;
        if (read_entry_at(fs, i, &e) != 0) {
            pthread_mutex_unlock(&fs->disk_lock);
            return -1;
        }
        if (e.type == TYPE_FILE) {
            printf("%-16s %-10u %-10u %-15s %-15s\n", e.name, e.size, e.start_cluster, e.created, e.modified);
            count++;
        }
    }

    if (count == 0) printf("No hay archivos registrados en el directorio.\n");
    printf("\n");

    pthread_mutex_unlock(&fs->disk_lock);
    return 0;
}

// Extrae un archivo de FiUnamFS
int fs_copy_from_fs(FiUnamFS *fs, const char *name, const char *dest_dir) {
    pthread_mutex_lock(&fs->disk_lock);

    DirEntry e;
    if (find_entry(fs, name, &e) < 0) {
        fprintf(stderr, "No existe el archivo '%s' dentro de FiUnamFS.\n", name);
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    char output_path[512];
    if (dest_dir && strlen(dest_dir) > 0) {
        snprintf(output_path, sizeof(output_path), "%s/%s", dest_dir, e.name);
    } else {
        snprintf(output_path, sizeof(output_path), "%s", e.name);
    }

    FILE *out = fopen(output_path, "wb");
    if (!out) {
        fprintf(stderr, "No se pudo crear '%s': %s\n", output_path, strerror(errno));
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    if (fseek(fs->disk, cluster_offset(fs, e.start_cluster), SEEK_SET) != 0) {
        fclose(out);
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    unsigned char buffer[4096];
    uint32_t remaining = e.size;
    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
        if (fread(buffer, 1, chunk, fs->disk) != chunk) {
            fclose(out);
            pthread_mutex_unlock(&fs->disk_lock);
            return -1;
        }
        if (fwrite(buffer, 1, chunk, out) != chunk) {
            fclose(out);
            pthread_mutex_unlock(&fs->disk_lock);
            return -1;
        }
        remaining -= (uint32_t)chunk;
    }

    fclose(out);
    printf("Archivo copiado desde FiUnamFS: %s\n", output_path);

    pthread_mutex_unlock(&fs->disk_lock);
    return 0;
}

// Copia un archivo local hacia FiUnamFS
int fs_copy_to_fs(FiUnamFS *fs, const char *local_path, const char *fs_name_arg) {
    char fs_name[MAX_NAME_LEN + 1];
    FILE *in = fopen(local_path, "rb");
    if (!in) {
        fprintf(stderr, "No se pudo abrir '%s': %s\n", local_path, strerror(errno));
        return -1;
    }

    if (fs_name_arg && strlen(fs_name_arg) > 0) {
        snprintf(fs_name, sizeof(fs_name), "%s", fs_name_arg);
    } else {
        basename_simple(local_path, fs_name, sizeof(fs_name));
    }

    if (!fs_valid_name(fs_name)) {
        fprintf(stderr, "Nombre invalido. Debe ser ASCII simple y medir maximo 15 caracteres.\n");
        fclose(in);
        return -1;
    }

    fseek(in, 0, SEEK_END);
    long size_long = ftell(in);
    rewind(in);
    if (size_long < 0 || size_long > UINT32_MAX) {
        fprintf(stderr, "El archivo local es demasiado grande.\n");
        fclose(in);
        return -1;
    }
    uint32_t size = (uint32_t)size_long;

    pthread_mutex_lock(&fs->disk_lock);

    if (find_entry(fs, fs_name, NULL) >= 0) {
        fprintf(stderr, "Ya existe un archivo llamado '%s' en FiUnamFS.\n", fs_name);
        pthread_mutex_unlock(&fs->disk_lock);
        fclose(in);
        return -1;
    }

    long free_entry_offset;
    if (find_free_entry(fs, &free_entry_offset) != 0) {
        fprintf(stderr, "No hay entradas libres en el directorio.\n");
        pthread_mutex_unlock(&fs->disk_lock);
        fclose(in);
        return -1;
    }

    int needed = clusters_needed(size, fs->cluster_size);
    int start_cluster = find_contiguous_space(fs, needed);
    if (start_cluster < 0) {
        fprintf(stderr, "No hay espacio contiguo suficiente para guardar el archivo.\n");
        pthread_mutex_unlock(&fs->disk_lock);
        fclose(in);
        return -1;
    }

    if (fseek(fs->disk, cluster_offset(fs, (uint32_t)start_cluster), SEEK_SET) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        fclose(in);
        return -1;
    }

    unsigned char buffer[4096];
    uint32_t remaining = size;
    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
        if (fread(buffer, 1, chunk, in) != chunk) {
            pthread_mutex_unlock(&fs->disk_lock);
            fclose(in);
            return -1;
        }
        if (fwrite(buffer, 1, chunk, fs->disk) != chunk) {
            pthread_mutex_unlock(&fs->disk_lock);
            fclose(in);
            return -1;
        }
        remaining -= (uint32_t)chunk;
    }

    if (write_file_entry(fs, free_entry_offset, fs_name, size, (uint32_t)start_cluster) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        fclose(in);
        return -1;
    }

    printf("Archivo copiado hacia FiUnamFS como '%s'.\n", fs_name);

    pthread_mutex_unlock(&fs->disk_lock);
    fclose(in);
    return 0;
}

// Libera la entrada del archivo eliminado
int fs_delete(FiUnamFS *fs, const char *name) {
    pthread_mutex_lock(&fs->disk_lock);

    DirEntry e;
    if (find_entry(fs, name, &e) < 0) {
        fprintf(stderr, "No existe el archivo '%s' dentro de FiUnamFS.\n", name);
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    if (write_empty_entry(fs, e.entry_offset) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    printf("Archivo eliminado del directorio: %s\n", name);
    pthread_mutex_unlock(&fs->disk_lock);
    return 0;
}


int fs_count_entries(FiUnamFS *fs) {
    return max_entries(fs);
}

int fs_get_entry_by_index(FiUnamFS *fs, int index, DirEntry *entry) {
    int total = max_entries(fs);
    if (index < 0 || index >= total) return -1;
    pthread_mutex_lock(&fs->disk_lock);
    int r = read_entry_at(fs, index, entry);
    pthread_mutex_unlock(&fs->disk_lock);
    return r;
}

int fs_get_entry_by_name(FiUnamFS *fs, const char *name, DirEntry *entry) {
    pthread_mutex_lock(&fs->disk_lock);
    int r = find_entry(fs, name, entry);
    pthread_mutex_unlock(&fs->disk_lock);
    return (r >= 0) ? 0 : -1;
}

// Lee contenido desde una posición específica
int fs_read_file(FiUnamFS *fs, const char *name, char *buffer, size_t size, off_t offset) {
    DirEntry e;
    pthread_mutex_lock(&fs->disk_lock);

    if (find_entry(fs, name, &e) < 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    if ((uint32_t)offset >= e.size) {
        pthread_mutex_unlock(&fs->disk_lock);
        return 0;
    }

    if (offset + (off_t)size > (off_t)e.size) {
        size = (size_t)((off_t)e.size - offset);
    }

    if (fseek(fs->disk, cluster_offset(fs, e.start_cluster) + offset, SEEK_SET) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    size_t readed = fread(buffer, 1, size, fs->disk);
    pthread_mutex_unlock(&fs->disk_lock);
    return (int)readed;
}

int fs_create_empty_file(FiUnamFS *fs, const char *name) {
    if (!fs_valid_name(name)) return -2;

    pthread_mutex_lock(&fs->disk_lock);
    if (find_entry(fs, name, NULL) >= 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -3;
    }

    long free_entry_offset;
    if (find_free_entry(fs, &free_entry_offset) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -4;
    }

    int start_cluster = find_contiguous_space(fs, 1);
    if (start_cluster < 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -5;
    }

    unsigned char zero[512];
    memset(zero, 0, sizeof(zero));
    if (fseek(fs->disk, cluster_offset(fs, (uint32_t)start_cluster), SEEK_SET) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }
    fwrite(zero, 1, sizeof(zero), fs->disk);

    int r = write_file_entry(fs, free_entry_offset, name, 0, (uint32_t)start_cluster);
    pthread_mutex_unlock(&fs->disk_lock);
    return r;
}

int fs_truncate_file(FiUnamFS *fs, const char *name, uint32_t new_size) {
    pthread_mutex_lock(&fs->disk_lock);

    DirEntry e;
    if (find_entry(fs, name, &e) < 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }

    int old_clusters = clusters_needed(e.size, fs->cluster_size);
    int new_clusters = clusters_needed(new_size, fs->cluster_size);
    if (new_clusters > old_clusters) {
        /* Esta implementación es sencilla: permite crecer el archivo sólo si los clusters siguientes están libres. */
        unsigned char *used = calloc(fs->total_clusters, 1);
        if (!used) {
            pthread_mutex_unlock(&fs->disk_lock);
            return -1;
        }
        for (uint32_t c = 0; c <= fs->dir_clusters && c < fs->total_clusters; c++) used[c] = 1;
        int total = max_entries(fs);
        for (int i = 0; i < total; i++) {
            DirEntry tmp;
            if (read_entry_at(fs, i, &tmp) != 0) { free(used); pthread_mutex_unlock(&fs->disk_lock); return -1; }
            if (tmp.type == TYPE_FILE && strcmp(tmp.name, name) != 0) {
                mark_used_clusters(fs, used, tmp.start_cluster, clusters_needed(tmp.size, fs->cluster_size));
            }
        }
        for (int i = old_clusters; i < new_clusters; i++) {
            uint32_t c = e.start_cluster + (uint32_t)i;
            if (c >= fs->total_clusters || used[c]) {
                free(used);
                pthread_mutex_unlock(&fs->disk_lock);
                return -2;
            }
        }
        free(used);
    }

    unsigned char raw[DIR_ENTRY_SIZE];
    if (fseek(fs->disk, e.entry_offset, SEEK_SET) != 0 || fread(raw, 1, DIR_ENTRY_SIZE, fs->disk) != DIR_ENTRY_SIZE) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }
    write_u32_le(raw + 16, new_size);
    char stamp[15];
    current_timestamp(stamp);
    memcpy(raw + 50, stamp, 14);
    if (fseek(fs->disk, e.entry_offset, SEEK_SET) != 0 || fwrite(raw, 1, DIR_ENTRY_SIZE, fs->disk) != DIR_ENTRY_SIZE) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }
    fflush(fs->disk);
    pthread_mutex_unlock(&fs->disk_lock);
    return 0;
}

// Escribe datos respetando el tamaño del archivo
int fs_write_file(FiUnamFS *fs, const char *name, const char *buffer, size_t size, off_t offset) {
    if (offset < 0) return -1;
    uint32_t final_size = (uint32_t)(offset + (off_t)size);

    DirEntry e;
    if (fs_get_entry_by_name(fs, name, &e) != 0) return -1;
    if (final_size > e.size) {
        if (fs_truncate_file(fs, name, final_size) != 0) return -2;
    }

    pthread_mutex_lock(&fs->disk_lock);
    if (find_entry(fs, name, &e) < 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }
    if (fseek(fs->disk, cluster_offset(fs, e.start_cluster) + offset, SEEK_SET) != 0) {
        pthread_mutex_unlock(&fs->disk_lock);
        return -1;
    }
    size_t written = fwrite(buffer, 1, size, fs->disk);
    fflush(fs->disk);
    pthread_mutex_unlock(&fs->disk_lock);
    return (int)written;
}
