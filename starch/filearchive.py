from json import loads
from os.path import exists,join,basename,dirname
from urllib.parse import urljoin
from os import remove,makedirs,walk
from shutil import rmtree
from starch.utils import convert,timestamp,valid_path,valid_key,get_temp_dirname,dict_search,TEMP_PREFIX
from random import random
import starch

MAX_ID=2**38

class FileArchive(starch.Archive):
    def __init__(self, root=None, base=None):
        self.temporary = root == None
        self.root_dir = root or get_temp_dirname()
        self.base = base


    def new(self, **kwargs):
        key = self._generate_key()
        dir = self._directory(key)
        p = starch.Package(dir, mode='w', base=self.base + key + '/' if self.base else None, **kwargs)

        self._log_add_package(key)

        return (key, p)


    def ingest(self, package, key=None):
        key = self._generate_key(suggest=valid_key(key) if key else None)
        dir = self._create_directory(key)
        self._lock(key)
        
        try:
            for path in package:
                self._copy(package.get_raw(path), join(dir, valid_path(path)))

            p = starch.Package(dir)
            p.validate()
        except Exception as e:
            rmtree(dir)
            raise e
        else:
            self._unlock(key)

        self._log_add_package(key)

        return key


    def patch(self, key, package):
        pass


    def get(self, key, mode='r'):
        if mode is 'w':
            raise Exception('mode \'w\' not allowed, use \'a\'')

        d = self._directory(key)

        if exists(d) and not self._is_locked(key):
            return starch.Package(d, mode=mode, base=urljoin(self.base, key + '/') if self.base else None)

        return None


    def get_location(self, key, path):
        d = self._directory(valid_key(key))
        p = join(d, valid_path(path))

        if exists(p) and not self._is_locked(key):
            return 'file://' + p
        else:
            return None


    def search(self, query=None, frm=0, max=None):
        # This is deliberatly non-optimal for small
        # resultsets in large archives and/or paging.
        # Use an index and the web frontend instead
        if max == 0:
            return

        n=0
        for key in self:
            p = self.get(key)

            if dict_search(query, p.description()):
                if n >= frm: 
                    yield key

                n += 1

                if max and max < n:
                    return


    def _directory(self, key):
        return join(self.root_dir, *[ key[2*i:2*i+2] for i in range(0,3) ], key)


    def _create_directory(self, key):
        dir = self._directory(key)
        makedirs(dir)

        return dir

    def _generate_key(self, suggest=None):
        key = suggest or convert(int(MAX_ID*random()), radix=28, pad_to=8)

        if exists(self._directory(key)):
            if suggest:
                raise Exception('key %s already exists')

            _log('warning: collision for key %s' % key)

            return self._generate_key()

        return key


    def _lock(self, key):
        if not self._is_locked(key):
            with open(join(self._directory(key), '_lock'), mode='w') as f:
                pass


    def _unlock(self, key):
        if self._is_locked(key):
            remove(join(self._directory(key), '_lock'))


    def __iter__(self):
        # @todo: better locking
        if exists(join(self.root_dir, 'packages')):
            with open(join(self.root_dir, 'packages')) as f:
                for line in f:
                    yield line[:-1]
        else:
            return iter([])


    def _log(self, message, t=timestamp()):
        with open("%s_log" % self.root_dir, 'a') as logfile:
            logfile.write(t + ' ' + message + '\n')


    def _key_exists(self, key):
        return exists(self._directory(key))


    def _is_locked(self, key):
        return exists(join(self._directory(key), '_lock'))


    def _log_add_package(self, key):
        # @todo: better locking
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


    def __del__(self):
        if self.temporary and self.root_dir.startswith(TEMP_PREFIX) and exists(self.root_dir):
            rmtree(self.root_dir)

