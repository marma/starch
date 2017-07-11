from contextlib import closing
from json import loads,dumps
from requests import head,get,post,delete,put
from os.path import basename,abspath,isdir
from starch.utils import valid_path,valid_key
from hashlib import sha256
import starch.package

VERSION = 0.1

class HttpPackage(starch.Package):
    def __init__(self, url, mode='r', auth=None):
        self.url = url
        self._mode = mode
        self.auth = auth

        if mode in [ 'r', 'a' ]:
            r = get(self.url, auth=self.auth)

            if r.status_code != 200:
                raise Exception('%d %s' % (r.status_code, r.text))

            self._desc = loads(r.text)

            if mode is 'a' and self._desc['status'] == 'finalized':
                raise Exception('package is finalized, use patch(...)')
        elif mode == 'w':
            raise Exception('mode \'w\' not supported for HttpPackage(), use \'a\'')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def add(self, fname, path=None, traverse=True, exclude='^\\..*|^_.*', replace=False, **kwargs):
        if self._mode != 'a':
            raise Exception('package not writable, open in \'a\' mode')

        path = path or basename(abspath(fname))

        if path == '_package.json' or path == '_log':
            raise Exception('path (%s) not allowed' % path)

        if traverse and isdir(fname):
            self._add_directory(fname, path, exclude=exclude)
        else:
            self._write(fname, valid_path(path), replace=replace, **kwargs)

        self._reload()


    def replace(self, fname, path=None, **kwargs):
        self.add(fname, path, replace=True, **kwargs)        


    def get_raw(self, path):
        r = get(self.url + path, stream=True, auth=self.auth)
        r.raw.decode_stream = True

        if r.status_code != 200:
            raise Exception('path (%s) not found' % path)

        return r.raw


    def read(self, path):
        return get(self.url + path, auth=self.auth).text


    def list(self):
        return list(self._desc['files'].keys())


    def finalize(self):
        if self._mode == 'r':
            raise Exception('package is in read-only mode')

        r = post(self.url + 'finalize', auth=self.auth)

        if r.status_code not in [ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))

        self._desc['status'] = 'finalized'
        self._mode = 'r'


    def close(self):
        self._mode = 'r'


    def _write(self, iname, path, replace=False):
        r = put(self.url + path, params={ 'replace': replace, 'expected_hash': do_hash(iname) }, files={ path: open(iname) }, auth=self.auth)

        if r.status_code not in[ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))
    

    def remove(self, path):
        r = delete(self.url + path, auth=self.auth)

        if r.status_code not in [ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))

        del self._desc['files'][path]


    def status(self):
        return self._desc['status']


    def _reload(self):
        self._desc = loads(get(self.url + '_package.json', auth=self.auth).text)


    def __iter__(self):
        return iter(self.list())


    def __contains__(self, key):
        return key in self._desc['files']


    def __getitem__(self, key):
        return self._desc['files'][key]


    def __setitem__(self, key, value):
        self._desc['files'][key] = value


    def __str__(self):
        return dumps(self._desc, indent=4)


def do_hash(fname):
    h = sha256()
    with open(fname, mode='rb') as f:
        b=None
        while b != b'':
            b = f.read(100*1024)
            h.update(b)

    return 'sha256:' + h.digest().hex()

