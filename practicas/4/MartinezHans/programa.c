#include <stdio.h>

int main() {
    FILE *f = fopen("salida.txt", "w");
    fprintf(f, "Hola desde la practica 4\n");
    fclose(f);
    return 0;
}