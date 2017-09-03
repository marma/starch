from json import dumps
from copy import deepcopy
from starch.utils import chunked
import starch.package

VERSION = 0.1

class MultiPackage(starch.Package):
    def __init__(self, package, with_patches=[], base=None):
        self.package = package
        self.patches = with_patches
        self.base = base
        self._desc=None


    def get_raw(self, path, range=None):
        for patch in reversed(self.patches):
            if path in patch:
                return patch.get_raw(path, range=range)

        if path in self.package:
            return self.package.get_raw(path, range=range)

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


    def get_iter(self, path, chunk_size=10*1024, range=None):
        if path in self:
            with self.get_raw(path, range=range) as f:
                yield from chunked(f, chunk_size=chunk_size, max=range[1]-range[0] if range and range[1] else None)
        else:
            raise Exception('%s does not exist in package' % path)


    def description(self):
        return self._desc if self._desc else self._description()


    def _description(self):
        ret = deepcopy(self.package.description(base=self.base))
        ret['has_patches'] = []

        for patch in self.patches:
            ret['has_patches'] += [ patch.description()['urn'] ]

            if patch.patch_type == 'version':
                ret['files'] = {}

            for path in patch:
                if 'operation' in patch[path] and patch[path]['operation'] == 'delete':
                    if path in ret['files']:
                        del(ret['files'][path])
                elif path not in [ '_package.json', '_log' ]:
                    ret['files'][path] = patch.get(path, base=self.base)

        if ret['has_patches'] == []:
            del(ret['has_patches'])

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


