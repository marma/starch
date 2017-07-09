from json import loads
from starch import Package
from os.path import exists,join,basename,dirname
from os import remove,makedirs,walk
from shutil import rmtree
from starch.utils import convert,timestamp,valid_path,valid_key
from random import random

MAX_ID=2**38

class Archive:
    def __init__(self, root_dir, encrypted=False, cert_path=None):
        self.root_dir = root_dir
        self.cert_path = cert_path
        self.encrypted = encrypted


    def new(self, **kwargs):
        key = self._generate_key()
        dir = self._directory(key)

        return (key, Package(dir, mode='w', encrypted=self.encrypted, cert_path=self.cert_path, **kwargs))


    def ingest(self, package, key=None):
        key = self._generate_key(suggest=valid_key(key) if key else None)
        dir = self._create_directory(key)
        self._lock(key)
        
        try:
            for path in package:
                self._copy(package.get_raw(path), join(dir, valid_path(path)))

            Package(dir).validate(validate_content=True, cert_path=self.cert_path)
        except Exception as e:
            rmtree(dir)
            raise e
        else:
            self._unlock(key)

        return key


    def get(self, key, mode='r'):
        d = self._directory(key)
        
        if exists(d) and not self._is_locked(key):
            return Package(d, mode=mode, encrypted=self.encrypted, cert_path=self.cert_path)

        return None

    def get_location(self, key, path):
        d = self._directory(valid_key(key))
        p = join(d, valid_path(path))

        if exists(p) and not self._is_locked(key):
            return 'file://' + p
        else:
            return None


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
        # this is non optimal
        for x in walk(self.root_dir):
            if '_package.json' in x[2] and '_lock' not in x[2]:
                yield basename(x[0])


    def _log(self, message, t=timestamp()):
        with open("%s_log" % self.root_dir, 'a') as logfile:
            logfile.write(t + ' ' + message + '\n')


    def _key_exists(self, key):
        return exists(self._directory(key))


    def _is_locked(self, key):
        return exists(join(self._directory(key), '_lock'))

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

