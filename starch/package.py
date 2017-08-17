import starch

VERSION = 0.1

class Package:
    def __new__(cls, first=None, **kwargs):
        if first and isinstance(first, starch.Package):
            return super(Package, starch.MultiPackage).__new__(starch.MultiPackage)
        if first and first.startswith('http'):
            return super(Package, starch.HttpPackage).__new__(starch.HttpPackage)
        else:
            return super(Package, starch.FilePackage).__new__(starch.FilePackage)

