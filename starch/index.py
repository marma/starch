import starch
from starch.utils import dict_search,dict_values,rebase
from collections import Counter
from copy import deepcopy

class Index():
    def __new__(cls, **kwargs):
        if ('type' in kwargs and kwargs['type'] == 'elastic') or ('url' in kwargs and 'index_name' in kwargs):
            return super().__new__(starch.ElasticIndex)
        elif 'type' not in kwargs or kwargs['type'] == 'memory':
            return super().__new__(starch.MemoryIndex)

        raise Exception('Unknown index type')


class MemoryIndex(Index):
    def __init__(self, type='memory', base=None, index_base=None):
        self.base = base
        self.index_base = index_base
        self.index = {}


    def get(self, key):
        if key in self.index:
            return rebase(self.index.get(key), self.index, self.index_base)
        else:
            return None


    def update(self, key, package):
        self.index[key] = package.description()


    def delete(self, key):
        if key in self.index:
            del(self.index[key])


    def search(self, query, start=0, max=None, sort=None):
        hits = [ x for x in self._search_iterator(query, start, max, sort) ]
        max = max or len(hits)

        if start >= len(hits):
            return (start, 0, len(hits), iter([]))

        return (start, min(max, len(hits), len(hits) - start), len(hits), iter(hits[start:start + max]))


    def count(self, query, cats):
        ret = { k:Counter() for k in cats }

        for key in self.search(query)[3]:
            desc = self.get(key)

            for key in cats:
                ret[key].update(dict_values(desc, cats[key]))
            
        return ret


    def iter_packages(self, start=0, max=None):
        for i,key in enumerate(self.index):
            if i >= start:
                if i - start < max:
                    yield key
                else:
                    return


    def _search_iterator(self, query, start=0, max=None, sort=None):
        for key in self.index:
            if dict_search(query, self.get(key)):
                yield key


    def destroy(self):
        pass

