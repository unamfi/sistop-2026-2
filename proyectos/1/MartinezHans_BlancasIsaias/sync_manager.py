import time


def directory_monitor(fs):

    for i in range(3):

        print("\n[THREAD] Monitoreando directorio...\n")

        fs.list_directory()

        time.sleep(2)


def copy_task(fs):

    time.sleep(1)

    fs.copy_from_fs("logo.png")
