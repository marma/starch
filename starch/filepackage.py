from os.path import exists,dirname,abspath,join,basename,isdir,join
from os import makedirs, walk, listdir, sep, remove
from urllib.request import urlopen
from urllib.parse import urlparse,urljoin,quote,unquote
from copy import deepcopy,copy
from uuid import uuid4
from starch.utils import get_temp_dirname,valid_path,valid_file,valid_key,TEMP_PREFIX,chunked,nullcallback
from contextlib import closing
from hashlib import md5,sha256
from random import random
from datetime import datetime
from io import BytesIO
from re import compile
from json import load,loads,dumps
from magic import Magic,MAGIC_MIME,MAGIC_RAW
from shutil import move,rmtree
import starch

VERSION = 0.1

class FilePackage(starch.Package):
    def __init__(self, root_dir=None, mode='r', base=None, patches=None, patch_type='supplement', callback=nullcallback, tags=[], label=None, **kwargs):
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
        self.callback = callback

        if mode == 'w':
            if exists(self.root_dir):
                raise Exception('path \'%s\' exists, use \'a\' mode' % self.root_dir)

            makedirs(self.root_dir)
            self._desc = {
                            '@id': '',
                            '@type': 'Package' if not patches else 'Patch',
                            'label': label,
                            'tags': tags,
                            'patches': patches,
                            'patch_type': patch_type,
                            'urn': uuid4().urn,
                            'described_by': '_package.json',
                            'status': 'open',
                            'package_version': VERSION,
                            'created': None,
                            'version': uuid4().urn,
                            'size': 0,
                            'files': { }
                         }

            if not patches:
                del(self._desc['patches'])
                del(self._desc['patch_type'])

            self._desc['created'] = datetime.utcnow().isoformat() + 'Z'
            self._log('CREATED %s' % self._desc['urn'], t=self._desc['created'])
            self.save()
        elif mode in [ 'r', 'a' ]:
            with open(self._get_full_path('_package.json')) as r:
                self._desc = loads(r.read())
                #print(self._desc)
                self._desc['files'] = { v['path']:v for v in self._desc['files'] }

            if mode is 'a' and self.is_finalized():
                raise Exception('package is finalized, use patch(...)')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def add(self, fname=None, path=None, data=None, traverse=True, check_version=None, exclude='^\\..*|^_.*', replace=False, **kwargs):
        if self._mode not in [ 'w', 'a' ]:
            raise Exception('package not writable, open in \'a\' mode')

        if not (fname or (path and data)):
            raise Exception('Specify either path to a filename or path and data)')

        with self._lock_ctx():
            #if check_version and check_version != self._desc['version']:
            #    raise Exception()

            path = path or basename(abspath(fname))

            if path in [ '_package.json', '_log' ]:
                raise Exception('filename (%s) not allowed' % path)

            if fname and traverse and isdir(fname):
                self._add_directory(fname, valid_path(path), exclude=exclude)
            else:
                f = self._write(valid_path(path), iname=fname, data=data, replace=replace)
                f.update(kwargs)
        
                self._desc['files'][path] = f
                self._log('STORE "%s" size:%i %s' % (path, f['size'], f['checksum']))
                self.save()
                


    def remove(self, path):
        if self._mode == 'r':
            raise Exception('package in read-only mode')

        if self.is_finalized():
            raise Exception('package is finalized, use patches')

        with self._lock_ctx():
            if path in self:
                del self._desc['files'][path]
                full_path = self._get_full_path(path)

                if exists(full_path):
                    remove(full_path)
            
            elif self.patches:
                self[path] = { '@id': path, 'operation': 'delete', 'path': path }
            else:
                raise Exception('path (%s) not found in package' % path)

            self._log('DELETE %s' % path)
            self.save()


    def replace(self, fname, path=None, **kwargs):
        self.add(fname, path, replace=True, **kwargs)        


    def get(self, path, base=None):
        ret = deepcopy(self._desc['files'][path])

        if base or self.base:
            ret['@id'] = (base or self.base) + ret['@id']

        return ret


    def get_location(self, path):
        if path in self:
            return 'file://' + self._get_full_path(path)

        raise Exception('%s does not exist in package' % path)


    def get_raw(self, path, range=None):
        if path in self:
            f = open(self._get_full_path(path), mode='rb')

            if range:
                f.seek(range[0])
            
            return f
        
        raise Exception('%s does not exist in package' % path)


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
        if path in self:
            with open(self._get_full_path(path)) as o:
                return o.read()

        raise Exception('%s does not exist in package' % path)


    def save(self):
        if self._mode in [ 'w', 'a' ]:
            desc = copy(self._desc)
            desc['version'] =  uuid4().urn
            desc['size'] = sum([ v['size'] for k,v in self._desc['files'].items() ])

            # de-dict files
            desc['files'] = [ x for x in desc['files'].values() ]

            with open(join(self.root_dir, '_package.json'), 'wb') as out:
                out.write(dumps(desc, indent=4).encode('utf-8'))

            self._desc['size'] = desc['size']
            self._desc['version'] = desc['version']
            self._log('VERSION', desc['version'])

            self.callback('save')
        else:
            Exception('package in read-only mode')


    def list(self):
        return list(self._desc['files'].keys())


    def finalize(self):
        if self._mode == 'r':
            raise Exception('package in read-only mode')

        if not self.is_finalized():
            self._desc['status'] = 'finalized'
            self.save()
            self._log("FINALIZED")
            self._mode = 'r'


    def close(self):
        self._mode = 'r'


    def validate(self):
        for path in self:
            pass

        return True

    @property
    def label(self):
        return self._desc['label']

    @label.setter
    def label(self, label):
        ltmp = self.label

        try:
            self._desc['label'] = label
            self.save()
            self._log('CHANGED LABEL', f'from "{ltmp}" to "{label}"')
        except Exception as e:
            self._desc['label'] = ltmp
            raise e

        return ltmp


    def status(self):
        return self._desc['status']


    def is_finalized(self):
        return self._desc['status'] == 'finalized'


    def description(self, include=[]):
        ret = deepcopy(self._desc)

        if self.base:
            ret['@id'] = self.base
            
            for path in ret['files']:
                f = ret['files'][path]
                f['@id'] = urljoin(self.base, f['@id'])

        # de-dict files
        ret['files'] = [ x for key,x in ret['files'].items() ]

        # include special files?
        for fname in include:
            if fname in self:
                with self.get_raw(fname) as f:
                    ret[fname[1:]] = load(f)

        return ret


    @property
    def urn(self):
        return self._desc['urn']


    def tag(self, tag):
        if self._mode in [ 'a', 'w' ]:
            if tag not in self._desc['tags']:
                self._desc['tags'] += [ tag ]

            self._log('TAG', tag)
            self.save()
        else:
            raise Exception('package in read-only mode')


    def untag(self, tag):
        if self._mode in [ 'a', 'w' ]:
            self._desc['tags'] = [ x for x in self._desc['tags'] if x != tag ]
            self._log('UNTAG', tag)
            self.save()
        else:
            raise Exception('package in read-only mode')


    def _lock_ctx(self):
        return self.callback('lock')


    def log(self):
        with open(self._get_full_path('_log'), 'r') as logfile:
            return logfile.read()


    def _log(self, *args, t=None):
        t = t or (datetime.utcnow().isoformat() + 'Z')

        message = ' '.join(args)

        if self._mode in [ 'a', 'w' ]:
            with open(self._get_full_path('_log'), 'a') as logfile:
                logfile.write(t + ' ' + message + '\n')
        else:
            raise Exception('package in read-only mode')


    def _get_full_path(self, path):
        return join(self.root_dir, path)


    def _add_directory(self, dir, path, exclude='^\\..*|^_.*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(sep.join([ dir, f ]), path=sep.join([ path, f ]), exclude=exclude)


    def _write(self, path, iname=None, data=None, replace=False):
        if not (iname or data):
            raise Exeption('Either iname or data need to be passed')

        oname = join(self.root_dir, path)

        if not replace and exists(oname):
            raise Exception('file (%s) already exists, use replace' % path)

        if not exists(dirname(oname)):
            makedirs(dirname(oname))

        temppath = join(self.root_dir, path + str(random()))

        f = { '@id': quote(path), 'urn': uuid4().urn, '@type': 'Resource', 'path': path}
        h = sha256()

        try:
            if iname:
                with open(iname, 'rb') as stream:
                    with open(temppath, 'wb') as out:
                        data, length = None, 0

                        while data != b'':
                            data = stream.read(100*1024)
                            out.write(data)
                            h.update(data)
                            size = out.tell()
            else:
                data = dumps(data) if isinstance(data, dict) or isinstance(data, list) else data
                data = data.encode('utf-8') if isinstance(data, str) else data

                with open(temppath, 'wb') as out:
                    h.update(data)
                    out.write(data)
                    size = len(data)
        except:
            raise
        else:
            f['size'] = size
            f['checksum'] = 'SHA256:' + h.hexdigest()

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

    def __repr__(self):
        return 'FilePackage<%s>' % self.urn

#    def __len__(self):
#        return len(self._desc['files'])

