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
        self._desc=self._description()


    def get_raw(self, path, range=None):
        if path in self:
            for patch in reversed(self.patches):
                if path in patch:
                    return patch.get_raw(path, range=range)

            if path in self.package:
                return self.package.get_raw(path, range=range)

        raise Exception('path (%s) does not exist in package' % path)


    def get_iter(self, path, chunk_size=10*1024, range=None):
        with self.get_raw(path, range=range) as f:
            yield from chunked(f, chunk_size=chunk_size, max=range[1]-range[0] + 1 if range and range[1] else None)


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
        ret = deepcopy(self._desc)
        ret['files'] = [ v for k,v in ret['files'].items() ]

        return ret


    def _description(self):
        ret = self.package.description()
        ret['files'] = { v['path']:v for v in ret['files'] }
        ret['instances'] = [ ret['urn'] ]

        for patch in self.patches:
            ret['instances'] += [ patch.description()['urn'] ]

            if patch.patch_type == 'version':
                ret['files'] = {}
                ret['tags'] = []
                ret['label'] = patch.description()['label']

            s = set(ret['tags'])
            s.update(patch.description()['tags'])
            ret['tags'] = list(s)

            if patch.description()['label']:
                ret['label'] = patch.description()['label']

            for path in patch:
                if 'operation' in patch[path] and patch[path]['operation'] == 'delete':
                    if path in ret['files']:
                        del(ret['files'][path])
                else:
                    ret['files'][path] = patch.get(path, base=self.base)

        if ret['instances'] == []:
            del(ret['instances'])

        ret['size'] = sum([ v['size'] for k,v in ret['files'].items() ])
        self._desc = ret

        return ret


    def close(self):
        ...


    def status(self):
        return self.description()['status']


    def __iter__(self):
        return iter(self.list())


    def __contains__(self, key):
        return key in self._desc['files'] and \
               'operation' in self[key] and \
               self[key]['operation'] != 'delete'


    def __getitem__(self, key):
        return self.description()['files'][key]


    def __str__(self):
        return dumps(self.description(), indent=4)


