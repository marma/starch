from os.path import exists,dirname,abspath,join,basename,isdir,join
from os import makedirs, walk, listdir, sep, remove
from urllib.request import urlopen
from urllib.parse import urlparse,urljoin,quote
from copy import deepcopy
from uuid import uuid4
from starch.utils import get_temp_dirname,valid_path,valid_file,valid_key,TEMP_PREFIX
from contextlib import closing
from hashlib import md5,sha256
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
    def __init__(self, root_dir=None, mode='r', base=None, patches=None, patch_type='supplement', metadata={}, **kwargs):
        if root_dir == None and mode == 'r':
            raise Exception('\'%s\' mode and empty dir not allowed' % mode)

        if patches and mode in [ 'r', 'a' ]:
            raise Exception('only new packages can use the patch-parameter')

        self._temporary = root_dir == None
        self._mode=mode
        self.root_dir=abspath(root_dir or get_temp_dirname()) + sep
        self.patches = patches
        self.patch_type = patch_type if patches else None
        self.base = base

        if mode == 'w':
            if exists(self.root_dir):
                raise Exception('path \'%s\' exists, use \'a\' mode' % self.root_dir)

            makedirs(self.root_dir)
            self._desc = { '@id': '',
                           '@type': 'Package' if not patches else 'Patch',
                           'patches': patches,
                           'patch_type': patch_type,
                           'urn': uuid4().urn,
                           'described_by': '_package.json',
                           'status': 'open',
                           'package_version': VERSION,
                           'metadata': metadata,
                           'created': None,
                           'files': {
                               '_package.json': {
                                   '@id': '_package.json',
                                   'urn': uuid4().urn,
                                   '@type': 'Resource',
                                   'mime_type': 'application/json',
                                   'path': '_package.json' },
                                '_log': {
                                    '@id': '_log',
                                    'urn': uuid4().urn,
                                    '@type': 'Resource',
                                    'mime_type': 'text/plain',
                                    'path': '_log' }
                                }
                           }

            if not patches:
                del(self._desc['patches'])
                del(self._desc['patch_type'])

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

        if path in [ '_package.json', '_log' ] or path.startswith('_patches'):
            raise Exception('filename (%s) not allowed' % path)

        if traverse and isdir(fname):
            self._add_directory(fname, valid_path(path), exclude=exclude)
        else:
            f = self._write(fname, valid_path(path), replace=replace)
            f.update(kwargs)
    
            self._desc['files'][path] = f
            self._log('STORE "%s" size:%i %s' % (path, f['size'], f['checksum']))
            self.save()


    def remove(self, path):
        if self._mode == 'r':
            raise Exception('package in read-only mode')

        if self.is_finalized():
            raise Exception('package is finalized, use patch(...)')

        if path in self:
            del self._desc['files'][path]
            full_path = self._get_full_path(path)

            if exists(full_path):
                remove(full_path)
        
            self._log('DELETE %s' % path)
            self.save()
        elif self.patches:
            self[path] = { '@id': path, 'operation': 'delete', 'path': path }
        else:
            raise Exception('path (%s) not found in package' % path)


    def replace(self, fname, path=None, **kwargs):
        self.add(fname, path, replace=True, **kwargs)        


    def get(self, path, base=None):
        ret = deepcopy(self._desc['files'][path])

        if base or self.base:
            ret['@id'] = (base or self.base or '') + ret['@id']

        return ret


    def get_raw(self, path):
        if not exists(self._get_full_path(path)):
            raise Exception('%s does not exist in package' % path)

        return open(self._get_full_path(path), mode='rb')


    def read(self, path):
        if not exists(self._get_full_path(path)):
            raise Exception('%s does not exist in package' % path)

        with open(self._get_full_path(path)) as o:
            return o.read()


    def save(self):
        if self._mode in [ 'w', 'a' ]:
            with open(join(self.root_dir, '_package.json'), 'w') as out:
                out.write(dumps(self._desc, indent=4))
        else:
            Exception('package in read-only mode')


    def list(self):
        return list(self._desc['files'].keys())


    def finalize(self):
        if self._mode == 'r':
            raise Exception('package in read-only mode')

        if not self.is_finalized():
            self._desc['status'] = 'finalized'
            self._log("FINALIZED")
            self.save()
            self._mode = 'r'


    def close(self):
        self._mode = 'r'


    def validate(self):
        for path in self:
            pass

        return True


    def status(self):
        return self._desc['status']


    def is_finalized(self):
        return self._desc['status'] == 'finalized'


    def description(self, base=None):
        ret = deepcopy(self._desc)
        base = base or self.base

        if base:
            ret['@id'] = base
            
            for path in ret['files']:
                f = ret['files'][path]
                f['@id'] = urljoin(base, f['@id'])

        return ret


    def _log(self, message):
        if self._mode in [ 'a', 'w' ]:
            with open(self._get_full_path('_log'), 'a') as logfile:
                t = datetime.utcnow()
                logfile.write(t.isoformat() + 'Z' + ' ' + message + '\n')
        else:
            Exception('package in read-only mode')


    def _get_full_path(self, path):
        return join(self.root_dir, path)


    def _add_directory(self, dir, path, exclude='^\\..*|^_.*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(sep.join([ dir, f ]), path=sep.join([ path, f ]), exclude=exclude)


    def _write(self, iname, path, replace=False):
        oname = join(self.root_dir, path)

        if not replace and exists(oname):
            raise Exception('file (%s) already exists, use replace' % path)

        if not exists(dirname(oname)):
            makedirs(dirname(oname))

        temppath = join(self.root_dir, path + str(random()))

        f = { '@id': quote(path), 'urn': uuid4().urn, '@type': 'Resource', 'path': path}
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
            raise
        else:
            f['size'] = size
            f['checksum'] = 'sha256:' + h.hexdigest()

            if path in self and self[path]['checksum'] == f['checksum']:
                f = self[path]
            else:
                move(temppath, oname)

                with Magic(flags=MAGIC_MIME) as m:
                    f['mime_type'] = m.id_filename(oname).split(';')[0]
        finally:
            if exists(temppath):
                remove(temppath)

        return f


    def __iter__(self):
        return iter(self.list())


    def __contains__(self, key):
        return key in self._desc['files']


    def __getitem__(self, path):
        return self.get(path)


    def __setitem__(self, key, value):
        self._desc['files'][key] = value


    def __str__(self):
        return dumps(self.description(), indent=4)


    def __del__(self):
        if self._temporary and exists(self.root_dir) and self.root_dir.startswith(TEMP_PREFIX):
            rmtree(self.root_dir)

