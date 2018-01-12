import starch

class Archive:
    def __new__(cls, root=None, **kwargs):
        if root:
            if isinstance(root, list) or isinstance(root, starch.Archive):
                return super(Archive, starch.MultiArchive).__new__(starch.MultiArchive)
            elif isinstance(root, str) and root.startswith('http'):
                return super(Archive, starch.HttpArchive).__new__(starch.HttpArchive)

        return super(Archive, starch.FileArchive).__new__(starch.FileArchive)

    def new(self):
        raise Exception('Not implemented')

    def get(self, key, mode='r'):
        raise Exception('Not implemented')

    def ingest(self, package, suggest_key=None):
        raise Exception('Not implemented')

    def search(self, query={}, start=0, max=None):
        raise Exception('Not implemented')

    def count(self, query={}, cats={}):
        raise Exception('Not implemented')

    def packages(self):
        raise Exception('Not implemented')

    #def lock(key, timeout=None):
    #    raise Exception('Not implemented')

    def __contains__(self, key):
        raise Exception('Not implemented')

    def __iter__(self):
        raise Exception('Not implemented')

