from contextlib import closing
from json import loads,dumps
from requests import head,get,post,delete,put
from os.path import join,basename,abspath,isdir
from starch.utils import valid_path,valid_key
from hashlib import sha256
from copy import deepcopy
from urllib.parse import urljoin
from re import compile
from os import listdir
import starch.package
from urllib.parse import urljoin
from werkzeug.urls import url_fix
from tempfile import TemporaryFile

VERSION = 0.1

class HttpPackage(starch.Package):
    def __init__(self, url, mode='r', base=None, auth=None, server_base=None):
        self.url = url
        self._mode = mode
        self.auth = auth
        self.base = base or url
        self.server_base = server_base or url

        if mode in [ 'r', 'a' ]:
            r = get(self.url, headers={ 'Accept': 'application/json' }, auth=self.auth)

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


    def description(self, rewrite_ids=False):
        ret = deepcopy(self._desc)
        server_base = self.server_base

        if self.base != server_base:
            ret['@id'] = ret['@id'].replace(server_base, self.base)

            for path in ret['files']:
                f = ret['files'][path]
                f['@id'] = f['@id'].replace(server_base, self.base)

        return ret


    def close(self):
        self._mode = 'r'


    def _write(self, iname, path, replace=False):
        with TemporaryFile(mode='wb+') as f, open(iname, mode='rb') as i:
            hasher = sha256()
            b = None
            while b == None or b != b'':
                b = i.read(100*1024)
                f.write(b)
                hasher.update(b)

            f.seek(0)

            r = put(url_fix(urljoin(self.url, path)),
                    params={ 'replace': replace,
                             'expected_hash': 'sha256:' + hasher.digest().hex() },
                    files={ path: f },
                    auth=self.auth)

            if r.status_code not in[ 200, 204 ]:
                raise Exception('%d %s' % (r.status_code, r.text))
    

    def remove(self, path):
        r = delete(self.url + path, auth=self.auth)

        if r.status_code not in [ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))

        del self._desc['files'][path]


    def status(self):
        return self._desc['status']


    def _add_directory(self, dir, path, exclude='^\\..*|^_.*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(join(dir, f), path=join(path, f), exclude=exclude)


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
        return dumps(self.description(), indent=4)


def do_hash(fname):
    h = sha256()
    with open(fname, mode='rb') as f:
        b=None
        while b != b'':
            b = f.read(100*1024)
            h.update(b)

    return 'sha256:' + h.digest().hex()

