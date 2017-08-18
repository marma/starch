from json import dumps
from copy import deepcopy
import starch.package

VERSION = 0.1

class MultiPackage(starch.Package):
    def __init__(self, package, with_patches=[], base=None):
        self.package = package
        self.patches = with_patches
        self.base = base
        self._desc=None


    def get_raw(self, path):
        for patch in reversed(self.patches):
            if path in patch:
                return patch.get_raw(path)

        if path in self.package:
            return self.package.get_raw(path)

        raise Exception('path (%s) not found' % path)


    def read(self, path):
        return self.get_raw(path).read()
       

    def list(self):
        ret = set(self.package.list())

        for patch in self.patches:
            if patch.patch_type == 'version':
                ret = set()

            ret = ret.union(set(patch.list()))

        return list(ret)


    def description(self):
        return self._desc if self._desc else self._description()


    def _description(self):
        ret = deepcopy(self.package.description(base=self.base))
        ret['patches'] = []

        for patch in self.patches:
            ret['patches'] += [ patch.description()['urn'] ]

            if patch.patch_type == 'version':
                ret['files'] = {}

            for path in patch:
                if 'operation' in patch[path] and patch[path]['operation'] == 'delete':
                    if path in ret['files']:
                        del(ret['files'][path])
                elif path not in [ '_package.json', '_log' ]:
                    ret['files'][path] = patch.get(path, base=self.base)

        if ret['patches'] == []:
            del(ret['patches'])

        self._desc = ret

        return ret


    def close(self):
        ...


    def status(self):
        return self.description()['status']


    def __iter__(self):
        return iter(self.list())


    def __contains__(self, key):
        return key in self.list()


    def __getitem__(self, key):
        return self.description()['files'][key]


    def __str__(self):
        return dumps(self.description(), indent=4)


