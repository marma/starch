import starch

class Archive:
    def __new__(cls, root=None, **kwargs):
        if root and (isinstance(root, list) or isinstance(root, starch.Archive)):
            return super(Archive, starch.MultiArchive).__new__(starch.MultiArchive)
        elif root and root.startswith('http'):
            return super(Archive, starch.HttpArchive).__new__(starch.HttpArchive)
        else:
            return super(Archive, starch.FileArchive).__new__(starch.FileArchive)

