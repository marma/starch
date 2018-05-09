from json import loads,dumps
from sys import stdin, stderr
from os.path import exists,join,basename,dirname
from urllib.parse import urljoin
from os import remove,makedirs,walk
from shutil import rmtree
from starch.utils import convert,timestamp,valid_path,valid_key,get_temp_dirname,dict_search,dict_values,TEMP_PREFIX
from random import random
from collections import Counter
from threading import RLock
import starch

MAX_ID=2**38

class FileArchive(starch.Archive):
    def __init__(self, root=None, base=None, index=None, lockm=starch.LockManager(type='null')):
        self.temporary = root == None
        self.root_dir = root or get_temp_dirname()
        self.base = base
        self.index = starch.Index(**index) if isinstance(index, dict) else index
        self.lockm = starch.LockManager(**lockm) if isinstance(lockm, dict) else lockm


    def new(self, **kwargs):
        key = self._generate_key()

        with self.lock(key):
            dir = self._directory(key)
            p = starch.Package(dir, mode='w', base=self.base + key + '/' if self.base else None, get_lock=self.lockm, **kwargs)
            p.callback = lambda msg, key=key, package=p, archive=self, **kwargs: archive._callback(msg, key=key, package=package)
            p.callback('new')

            self._log_add_package(key)

            return (key, p)


    def ingest(self, package, key=None):
        key = self._generate_key(suggest=valid_key(key) if key else None)

        with self.lockm.get(key):
            dir = self._create_directory(key)
            
            try:
                for path in package:
                    self._copy(package.get_raw(path), join(dir, valid_path(path)))

                with open(join(dir, '_package.json'), mode='w') as o:
                    o.write(dumps(package.description(), indent=2))

                # TODO make @ids relative in _package.json?
                # TODO make sure all meta-files get copied too

                p = starch.Package(dir)
                p.validate()
            except Exception as e:  
                rmtree(dir)
                raise e

            self._log_add_package(key)
            self._callback('ingest', key=key, package=p)

            return key


    def patch(self, key, package):
        with self.lockm.get(key):
            raise Exception('Not implemented')


    def get(self, key, mode='r'):
        if mode is 'w':
            raise Exception('mode \'w\' not allowed, use \'a\'')

        #print('GET:', key)
        d = self._directory(key)

        if exists(d):
            p=starch.Package(d, mode=mode, base=urljoin(self.base, key + '/') if self.base else None)
            p.callback=lambda msg, key=key, package=p, archive=self, **kwargs: archive._callback(msg, key=key, package=package)

            return p

        return None


    def get_location(self, key, path):
        d = self._directory(valid_key(key))
        p = join(d, valid_path(path))

        if exists(p):
            return 'file://' + p
        else:
            return None


    def search(self, query, start=0, max=None, sort=None):
        # This is deliberatly non-optimal for small
        # resultsets in large archives and/or paging.
        # Use an index and the web frontend instead
        #print(query)

        if self.index:
            return self.index.search(query, start, max, sort)

        hits = [ x for x in self._search_iterator(query, start, max, sort) ]
        max = max or len(hits)

        if start >= len(hits):
            return (start, 0, len(hits), iter([]))

        return (start, min(max, len(hits), len(hits) - start), len(hits), iter(hits[start:start + max]))


    def count(self, query, cats={}):
        if self.index:
            return self.index.count(query, cats)

        ret = { k:Counter() for k in cats }

        for key in self.search(query)[3]:
            desc = self.get(key).description()

            for key in cats:
                #print(dict_values(desc, cats[key]))
                ret[key].update(dict_values(desc, cats[key]))
            
        return ret


    def lock(self, key):
        return self.lockm.get(key)


    def _search_iterator(self, query, start=0, max=None, sort=None):
        for key in self:
            p = self.get(key)

            if dict_search(query, p.description()):
                yield key


    def _directory(self, key):
        return join(self.root_dir, *[ key[2*i:2*i+2] for i in range(0,3) ], key)


    def _create_directory(self, key):
        dir = self._directory(key)
        makedirs(dir)

        return dir


    def _generate_key(self, suggest=None):
        # TODO locking a central function and waiting for I/O, that
        # might take a long time to return, is non-optimal
        with self.lockm.get('keygen'):
            key = suggest or convert(int(MAX_ID*random()), radix=28, pad_to=8)

            if exists(self._directory(key)):
                if suggest:
                    raise Exception('key %s already exists')

                _log('warning: collision for key %s' % key)

                return self._generate_key()

            return key


    def __iter__(self):
        if exists(join(self.root_dir, 'packages')):
            with open(join(self.root_dir, 'packages')) as f:
                for line in f:
                    # prevent potential half-written last id from being returned
                    if line[-1] == '\n':
                        yield line[:-1]
        else:
            return iter([])


    def _log(self, message, t=timestamp()):
        with self.lockm.get('log'):
            with open(join(self.root_dir, '_log'), 'a') as logfile:
                logfile.write(t + ' ' + message + '\n')


    def _warning(self, message, t=timestamp()):
        with self.lockm.get('warning'):
            with open(join(self.root_dir, '_warning'), 'a') as logfile:
                logfile.write(t + ' ' + message + '\n')


    def _key_exists(self, key):
        return exists(self._directory(key))


    def _log_add_package(self, key):
        with self.lockm.get('packages'):
            with open(join(self.root_dir, 'packages'), 'a') as f:
                f.write(key + '\n')


    def _copy(self, s, loc):
        if exists(loc):
            raise Exception('location already exists (%s)' % s)

        if not exists(dirname(loc)):
            makedirs(dirname(loc))

        with s as i, open(loc, mode='bw') as o:
            b=None
            while b == None or b != b'':
                b = i.read(100*1024)
                o.write(b)


    def _callback(self, msg, key, package=None):
        #print('callback')
        if msg == 'lock':
            return self.lock(key)
        elif msg in [ 'new', 'save', 'ingest' ]:
            if self.index:
                #print('index %s' % key, file=stderr)
                self.index.update(key, package or self.get(key))


    def __del__(self):
        if self.temporary and self.root_dir.startswith(TEMP_PREFIX) and exists(self.root_dir):
            rmtree(self.root_dir)

            if self.index:
                self.index.destroy()

    def __str__(self):
        return repr([ self.root_dir, self.temporary, self.index, self.lockm ])


    def __getitem__(self, key):
        return self.get(key)

