# Se establecen variables del compilador
CC = gcc

# Banderas de compilación: 
# -Wall y -Wextra muestran advertencias.
CFLAGS = -Wall -Wextra -D_FILE_OFFSET_BITS=64 `pkg-config fuse3 --cflags`

# Bibliotecas empleadas: FUSE 3 y pthreads para sincronización de hilos.
LDFLAGS = `pkg-config fuse3 --libs` -lpthread

# Se definen nombre del ejecutable generado y código fuente en C
TARGET = fiunamfs
SRC = fiunamfs.c

# Regla por defecto
all: $(TARGET)

# Regla para compilar el ejecutable
$(TARGET): $(SRC)
	$(CC) $(CFLAGS) $(SRC) -o $(TARGET) $(LDFLAGS)

# Regla para limpiar los archivos generados
clean:
	rm -f $(TARGET)
