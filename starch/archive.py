import starch

class Archive:
    def __new__(cls, first=None, **kwargs):
        if first and (isinstance(first, list) or isinstance(first, starch.Archive)):
            return super(Archive, starch.MultiArchive).__new__(starch.MultiArchive)
        elif first and first.startswith('http'):
            return super(Archive, starch.HttpArchive).__new__(starch.HttpArchive)
        else:
            return super(Archive, starch.FileArchive).__new__(starch.FileArchive)

