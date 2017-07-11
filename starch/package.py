import starch

VERSION = 0.1

class Package:
    def __new__(cls, url=None, **kwargs):
        if url and url.startswith('http'):
            return super(Package, starch.HttpPackage).__new__(starch.HttpPackage)
        else:
            return super(Package, starch.FilePackage).__new__(starch.FilePackage)

