from contextlib import closing
from json import loads,dumps
from requests import head,get,post,delete,put
from os.path import join,basename,abspath,isdir
from starch.utils import valid_path,valid_key,chunked
from starch.exceptions import RangeNotSupported
from hashlib import sha256
from copy import deepcopy
from urllib.parse import urljoin,unquote
from re import compile
from os import listdir
import starch.package
from urllib.parse import urljoin
from werkzeug.urls import url_fix
from tempfile import TemporaryFile
from io import BytesIO

VERSION = 0.1

class HttpPackage(starch.Package):
    def __init__(self, url, mode='r', base=None, auth=None, server_base=None, label=None):
        self.url = url
        self._mode = mode
        self.auth = auth
        self.base = base or url
        self.server_base = server_base or url

        if mode in [ 'r', 'a' ]:
            with closing(get(self.url, headers={ 'Accept': 'application/json' }, auth=self.auth)) as r:
                #print(self.url)

                if r.status_code == 404:
                    raise starch.HttpNotFoundException(r.text)
                elif r.status_code != 200:
                    raise Exception('%d %s' % (r.status_code, r.text))

                self._desc = loads(r.text)

                if mode is 'a' and self._desc['status'] == 'finalized':
                    raise Exception('package is finalized, use patch(...)')

                self._desc['files'] = { x['path']:x for x in self._desc['files'] }
        elif mode == 'w':
            raise Exception('mode \'w\' not supported for HttpPackage(), use mode \'a\' or HttpArchive.new(...)')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def add(self, fname=None, path=None, data=None, traverse=True, exclude='^\\..*|^_.*', replace=False, type='Resource', **kwargs):
        if self._mode != 'a':
            raise Exception('package not writable, open in \'a\' mode')

        if not (fname or (path and data)):
            raise Exception('Specify either path to a filename or path and data)')

        path = path or basename(abspath(fname))

        if path == '_package.json' or path == '_log':
            raise Exception(f'path ({path}) not allowed')

        if fname and traverse and isdir(fname):
            self._add_directory(fname, path, exclude=exclude)
        else:
            self._write(valid_path(path), iname=fname, data=data, replace=replace, type=type)

        self._reload()


    def replace(self, fname, path=None, **kwargs):
        self.add(fname, path, replace=True, **kwargs)        


    def get_location(path):
        return self.url + path


    def get_raw(self, path, range=None):
        headers = {}

        if path not in self:
            raise Exception('%s does not exist in package' % path)

        if range and not (range[0] == 0 and not range[1]):
            headers['Range'] = 'bytes=%d-%s' % (range[0], str(int(range[1])) if range[1] else '')

        # @TODO potential resource leak
        r = get(get_location(path), stream=True, auth=self.auth, headers=headers)
        r.raw.decode_stream = True

        if range and 'bytes' not in r.headers.get('Accept-Ranges', ''):
            raise RangeNotSupported()

        if r.status_code not in [ 200, 206 ]:
            raise Exception('Unexpected status %d' % r.status_code)

        return r.raw


    def get_iter(self, path, chunk_size=10*1024, range=None):
        if path in self:
            return self._get_iter(
                        self.get_raw(path, range=range),
                        chunk_size=chunk_size,
                        max=range[1]-range[0] if range and range[1] else None)
        else:
            raise Exception('%s does not exist in package' % path)


    def _get_iter(self, raw, chunk_size=10*1024, max=None):
        with raw as f:
            yield from chunked(f, chunk_size=chunk_size, max=max)


    def read(self, path):
        return get(self.url + path, auth=self.auth).text


    def list(self):
        return list(self._desc['files'].keys())


    def tag(self, tag):
        if self._mode in [ 'a', 'w' ]:
            r = post(self.url + '_tag', data={ 'tag': tag }, auth=self.auth)

            if r.status_code != 200:
                raise Exception('expected 200, got %d with message "%s"' % (r.status_code, r.text))

            self._desc['tags'] += [ tag ]
            #self._reload()
        else:
            raise Exception('package in read-only mode')


    def untag(self, tag):
        if self._mode in [ 'a', 'w' ]:
            r = post(self.url + '_tag', data={ 'untag': tag }, auth=self.auth)

            if r.status_code != 200:
                raise Exception('expected 200, got %d with message "%s"' % (r.status_code, r.text))

            self._desc['tags'] = [ x for x in self._desc['tags'] if x != tag ]
            #self._reload()
        else:
            raise Exception('package in read-only mode')


    def finalize(self):
        if self._mode == 'r':
            raise Exception('package is in read-only mode')

        r = post(self.url + 'finalize', auth=self.auth)

        if r.status_code not in [ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))

        self._desc['status'] = 'finalized'
        self._mode = 'r'


    def description(self):
        ret = deepcopy(self._desc)
        server_base = self.server_base

        if self.base != server_base:
            ret['@id'] = ret['@id'].replace(server_base, self.base)

            for path in ret['files']:
                f = ret['files'][path]
                f['@id'] = f['@id'].replace(server_base, self.base)

        # de-dict
        ret['files'] = [ x for x in ret['files'].values() ]

        return ret


    def close(self):
        self._mode = 'r'


    def _write(self, path, iname=None, data=None, replace=False, type=type):
        if not (iname or data):
            raise Exeption('Either iname or data need to be passed')

        data = dumps(data) if isinstance(data, dict) or isinstance(data, list) else data
        data = data.encode('utf-8') if isinstance(data, str) else data

        with TemporaryFile(mode='wb+') as f, open(iname, mode='rb') if iname else BytesIO(data) as i:
            hasher = sha256()

            b = None
            while b == None or b != b'':
                b = i.read(100*1024)
                f.write(b)
                hasher.update(b)

            f.seek(0)

            r = put(url_fix(urljoin(self.url, path)),
                    params={ 'replace': replace,
                             'expected_hash': 'SHA256:' + hasher.digest().hex(),
                             'type': type },
                    files={ path: f },
                    auth=self.auth)

            if r.status_code not in[ 200, 204 ]:
                raise Exception('%d %s' % (r.status_code, r.text))


    def remove(self, path):
        r = delete(self.url + path, auth=self.auth)

        if r.status_code not in [ 200, 204 ]:
            raise Exception('%d %s' % (r.status_code, r.text))

        self._reload()
        #del self._desc['files'][path]


    def status(self):
        return self._desc['status']


    @property
    def label(self):
        return self._desc['label']


    @label.setter
    def label(self, label):
        if self._mode != 'a':
            raise Exception('package not writable, open in \'a\' mode')            

        ltmp = self.label

        try:
            self._desc['label'] = label
            r = post(self.url + '_label', data={ 'label': label }, auth=self.auth)

            if r.status_code != 200:
                raise Exception(f'Expected HTTP status 200, got {r.status_code}, data is "{r.text}"')

            self._reload()
        except Exception as e:
            self._desc['label'] = ltmp
            raise e

        return ltmp


    def _add_directory(self, dir, path, exclude='^\\..*|^_.*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(join(dir, f), path=join(path, f), exclude=exclude)


    def _reload(self):
        self._desc = loads(get(self.url, auth=self.auth).text)
        self._desc['files'] = { x['path']:x for x in self._desc['files'] }


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


#    def __len__(self):
#        return len(self._desc['files'])


def do_hash(fname):
    h = sha256()
    with open(fname, mode='rb') as f:
        b=None
        while b != b'':
            b = f.read(100*1024)
            h.update(b)

    return 'SHA256:' + h.digest().hex()

