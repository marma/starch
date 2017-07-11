import starch

class Archive:
    def __new__(cls, url=None, **kwargs):
        if url.startswith('http'):
            return super(Archive, starch.HttpArchive).__new__(starch.HttpArchive)
        else:
            return super(Archive, starch.FileArchive).__new__(starch.FileArchive)

