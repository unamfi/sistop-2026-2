class FiUnamFSError(Exception):
    pass


class DiskError(FiUnamFSError):
    pass


class SuperblockError(FiUnamFSError):
    pass


class DirectoryError(FiUnamFSError):
    pass


class FilesystemError(FiUnamFSError):
    pass
