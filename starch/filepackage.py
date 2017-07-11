from os.path import exists,dirname,abspath,join,basename,isdir,join
from os import makedirs, walk, listdir, sep, remove
from urllib.request import urlopen
from urllib.parse import urlparse
from uuid import uuid4
from starch.utils import get_temp_dirname,valid_path,valid_file,TEMP_PREFIX
from contextlib import closing
from hashlib import md5,sha1
from random import random
from datetime import datetime
from io import BytesIO
from re import compile
from json import loads,dumps
from magic import Magic,MAGIC_MIME,MAGIC_RAW
from shutil import move,rmtree
import starch

VERSION = 0.1

class FilePackage(starch.Package):
    def __init__(self, dir=None, mode='r', parent=None, auth=None, metadata={}, **kwargs):
        if dir == None and mode == 'r':
            raise Exception('\'%s\' mode and no dir not allowed' % mode)

        self.url='file://' + abspath(dir or get_temp_dirname()) + sep
        self._mode=mode
        self.temporary = dir == None

        if mode == 'w':
            if exists(self.url[7:]):
                raise Exception('path \'%s\' exists, use \'a\' mode' % dir)

            makedirs(self.url[7:])
            self._desc = { '@id': '.',
                           '@context': '/context.jsonld',
                           '@type': 'Package',
                           'key': None,
                           'urn': uuid4().urn,
                           'described_by': '_package.json',
                           'status': 'open',
                           'package_version': VERSION,
                           'metadata': metadata,
                           'files': { '_package.json': { '@id': '_package.json', 'urn': uuid4().urn, '@type': 'Resource', 'mime_type': 'application/json' },
                                      '_log': { '@id': '_log', 'urn': uuid4().urn, '@type': 'Resource', 'mime_type': 'text/plain' } } }

            self._desc['metadata'].update(kwargs)
            self._desc['created'] = datetime.utcnow().isoformat() + 'Z'
            self.save()
            self._log('CREATED')
        elif mode in [ 'r', 'a' ]:
            with open(self._get_full_path('_package.json')) as r:
                self._desc = loads(r.read())

            if mode is 'a' and self.is_finalized():
                raise Exception('package is finalized, use patch(...)')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def add(self, fname, path=None, traverse=True, exclude='^\\..*|^_.*', replace=False, **kwargs):
        if self._mode not in [ 'w', 'a' ]:
            raise Exception('package not writable, open in \'a\' mode')

        path = path or basename(abspath(fname))

        if path == '_package.json' or path == '_log':
            raise Exception('filename (%s) not allowed' % path)

        if traverse and isdir(fname):
            self._add_directory(fname, path, exclude=exclude)
        else:
            self._write(fname, valid_path(path), replace=replace)
            self._desc['files'][path].update(kwargs)
            self.save()


    def replace(self, fname, path=None, **kwargs):
        self.add(fname, path, replace=True, **kwargs)        


    def get_raw(self, path):
        if not exists(self._get_full_path(path)):
            raise Exception('%s does not exist in package' % path)

        return open(self._get_full_path(path), mode='rb')


    def read(self, path):
        if not exists(self._get_full_path(path)):
            raise Exception('%s does not exist in package' % path)

        with open(self._get_full_path(path)) as o:
            return o.read()


    def set_key(self, key):
        if self._mode not in [ 'w', 'a' ]:
            raise Exception('package in read-only mode, use \'a\'')

        self._desc['key'] = valid_(key)
        self._desc['@id'] = '/%s/' % key


    def _log(self, message):
        if self._mode in [ 'a', 'w' ]:
            with open(self._get_full_path('_log'), 'a') as logfile:
                t = datetime.utcnow()
                logfile.write(t.isoformat() + 'Z' + ' ' + message + '\n')
        else:
            Exception('package in read-only mode')


    def save(self):
        if self._mode in [ 'w', 'a' ]:
            with open(self.url[7:] + '_package.json', 'w') as out:
                out.write(str(self))
        else:
            Exception('package in read-only mode')


    def list(self):
        return list(self._desc['files'].keys())


    def finalize(self):
        if self._mode == 'r':
            raise Exception('package is in read-only mode')

        self._desc['status'] = 'finalized'
        self._log("FINALIZED")
        self.save()
        self._mode = 'r'


    def close(self):
        self._mode = 'r'


    def validate(self):
        return True


    def remove(self, path):
        if self._mode == 'r':
            raise Exception('package in read-only mode')

        if self.is_finalized():
            raise Exception('package is finalized, use patch(...)')

        if path in self._desc['files']:
            del self._desc['files'][path]
            full_path = self._get_full_path(path)
            if exists(full_path):
                remove(full_path)
        
            self._log('DELETE %s' % path)
            self.save()
        else:
            raise Exception('path (%s) not found in package' % path)


    def status(self):
        return self._desc['status']


    def is_finalized(self):
        return self._desc['status'] == 'finalized'


    def _get_full_path(self, path):
        return join(self.url[7:], path)


    def _add_directory(self, dir, path, exclude='^\\..*|^_.*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(sep.join([ dir, f ]), path=sep.join([ path, f ]), exclude=exclude)


    def _write(self, iname, path, replace=False):
        oname = join(self.url[7:], path)

        if not replace and exists(oname):
            raise Exception('file (%s) already exists, use replace' % path)

        if not exists(dirname(oname)):
            makedirs(dirname(oname))

        temppath = join(self.url[7:], path + str(random()))

        f = { '@id': path, 'urn': uuid4().urn, '@type': 'Resource' }
        h = sha256()

        try:
            with open(iname, 'rb') as stream:
                with open(temppath, 'wb') as out:
                    data, length = None, 0

                    while data != b'':
                        data = stream.read(100*1024)
                        out.write(data)
                        h.update(data)
                        size = out.tell()
        except:
            remove(temppath)
            raise
        else:
            try:
                move(temppath, oname)
            except:
                remove(temppath)
                raise

        f['size'] = size
        f['checksum'] = 'sha256:' + h.hexdigest()
        self._desc['files'][path] = f

        with Magic(flags=MAGIC_MIME) as m:
            f['mime_type'] = m.id_filename(oname).split(';')[0]

        self._log('STORE %s size:%i MD5:%s' % (path, size, h.hexdigest()))
        self.save()


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


    def __del__(self):
        if self.temporary and self.url.startswith('file://' + TEMP_PREFIX):
            rmtree(self.url[7:])


