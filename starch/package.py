import starch
from json import dumps

VERSION = 0.1

class Package:
    def __new__(cls, first=None, **kwargs):
        if first:
            if isinstance(first, starch.Package):
                return super(Package, starch.MultiPackage).__new__(starch.MultiPackage)
            elif first.startswith('http'):
                return super(Package, starch.HttpPackage).__new__(starch.HttpPackage)

        return super(Package, starch.FilePackage).__new__(starch.FilePackage)

    def add(self, filename=None, data=None, path=None, replace=False):
        raise Exception('Not implemented')

    def replace(self, filename=None, data=None, path=None):
        raise Exception('Not implemented')

    def delete(self, path):
        raise Exception('Not implemented')

    def description(self):
        raise Exception('Not implemented')

    def get_raw(self, path, range=None):
        raise Exception('Not implemented')

    def get_iter(self, path, range=None):
        raise Exception('Not implemented')

    #def get_location(self, path):
    #    raise Exception('Not implemented')

    def status(self):
        raise Exception('Not implemented')

    def finalize(self):
        raise Exception('Not implemented')

    def close(self):
        raise Exception('Not implemented')

    def version(self):
        raise Exception('Not implemented')

    def __contains__(self, path):
        raise Exception('Not implemented')

    def __iter__(self):
        raise Exception('Not implemented')

    def __getitem__(self, path):
        raise Exception('Not implemented')

    def __str__(self):
        return dumps(self.description(), indent=4)

