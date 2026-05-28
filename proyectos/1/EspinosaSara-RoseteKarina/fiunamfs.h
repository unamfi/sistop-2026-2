#ifndef FIUNAMFS_H
#define FIUNAMFS_H

#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <sys/types.h>

#define MAGIC_EXPECTED "FiUnamFS"
#define VERSION_EXPECTED "24-2"
#define MAX_NAME_LEN 15
#define DIR_ENTRY_SIZE 64
#define TYPE_FILE '-'
#define TYPE_FREE '/'

typedef struct {
    FILE *disk;
    char path[256];
    uint32_t cluster_size;
    uint32_t dir_clusters;
    uint32_t total_clusters;
    long dir_start;
    long data_start;
    pthread_mutex_t disk_lock;
} FiUnamFS;

typedef struct {
    char type;
    char name[MAX_NAME_LEN + 1];
    uint32_t size;
    uint32_t start_cluster;
    char created[15];
    char modified[15];
    long entry_offset;
} DirEntry;

int fs_open(FiUnamFS *fs, const char *disk_path);
void fs_close(FiUnamFS *fs);
int fs_list(FiUnamFS *fs);
int fs_copy_from_fs(FiUnamFS *fs, const char *name, const char *dest_dir);
int fs_copy_to_fs(FiUnamFS *fs, const char *local_path, const char *fs_name);
int fs_delete(FiUnamFS *fs, const char *name);

//Funciones reutilizadas por el módulo FUSE//
int fs_count_entries(FiUnamFS *fs);
int fs_get_entry_by_index(FiUnamFS *fs, int index, DirEntry *entry);
int fs_get_entry_by_name(FiUnamFS *fs, const char *name, DirEntry *entry);
int fs_read_file(FiUnamFS *fs, const char *name, char *buffer, size_t size, off_t offset);
int fs_write_file(FiUnamFS *fs, const char *name, const char *buffer, size_t size, off_t offset);
int fs_create_empty_file(FiUnamFS *fs, const char *name);
int fs_truncate_file(FiUnamFS *fs, const char *name, uint32_t new_size);
int fs_valid_name(const char *name);

#endif
