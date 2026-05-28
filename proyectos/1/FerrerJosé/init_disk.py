import struct

CLUSTER_SIZE = 2048
TOTAL_CLUSTERS = 720
DISK_SIZE = CLUSTER_SIZE * TOTAL_CLUSTERS

with open("fiunamfs.img", "wb") as f:
    f.write(b"\x00" * DISK_SIZE)

with open("fiunamfs.img", "r+b") as f:
    superblock = bytearray(CLUSTER_SIZE)

    superblock[5:13] = b"FiUnamFS"
    superblock[14:18] = b"26-2"

    superblock[40:44] = struct.pack("<I", CLUSTER_SIZE)
    superblock[50:54] = struct.pack("<I", 8)
    superblock[60:64] = struct.pack("<I", TOTAL_CLUSTERS)

    f.seek(0)
    f.write(superblock)

ENTRY_SIZE = 64

with open("fiunamfs.img", "r+b") as f:
    for cluster in range(1, 9):
        f.seek(cluster * CLUSTER_SIZE)
        block = bytearray(CLUSTER_SIZE)

        for i in range(0, CLUSTER_SIZE, ENTRY_SIZE):
            block[i] = ord('/')
            block[i+1:i+16] = b"###############"

        f.write(block)

print("Disco inicializado correctamente.")