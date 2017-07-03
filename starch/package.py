from os.path import exists,dirname,abspath,join,basename,isdir,join
from os import makedirs, walk, listdir, sep
from urllib.request import urlopen
from urllib.parse import urlparse
from uuid import uuid4
from starch.utils import random_slug,normalize_url,get_temp_dirname
from contextlib import closing
from hashlib import md5,sha1
from random import random
from datetime import datetime
from io import BytesIO
from re import compile
from json import loads,dumps
from magic import Magic,MAGIC_MIME,MAGIC_RAW

VERSION = 0.1

class Package:
    def __init__(self, dir=None, mode='r', id=None, auth=None, parent=None, metadata={}, **kwargs):
        if not dir and mode is 'r':
            raise Exception('\'%s\' mode and no dir not allowed' % mode)

        self.url = 'file://' + abspath(dir or get_temp_dirname()) + sep
        self.mode = mode

        if mode == 'w':
            if exists(self.url[7:]):
                raise Exception('path \'%s\' exists, use \'a\' mode' % dir)

            makedirs(self.url[7:])
            self._desc = { '@id': id or '.',
                           '@context': '/context.jsonld',
                           '@type': 'Package',
                           'urn': uuid4().urn,
                           'described_by': 'package.json',
                           'status': 'open',
                           'package_version': VERSION,
                           'metadata': metadata,
                           'files': { 'package.json': { '@id': 'package.json', 'urn': uuid4().urn, '@type': 'Resource', 'mime_type': 'application/json' }} }
                
            self._desc['metadata'].update(kwargs)
            self._desc['created'] = datetime.utcnow().isoformat() + 'Z'
            self.save()
            self._log('CREATED')
        elif mode in [ 'r', 'a' ]:
            with get(url, auth=auth) as r:
                self._desc = loads(r.text)

            if mode is 'a' and self._desc['status'] == 'finalized':
                raise Exception('packet is finalized, use patch(...)')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def add(self, fname, path=None, traverse=True, exclude='^\\..*'):
        if self.mode not in [ 'w', 'a' ]: raise Exception('package not writable')
        path = path or basename(abspath(fname))

        if traverse and isdir(fname):
            self._add_directory(fname, path, exclude=exclude)
        else:
            if path and (path[0] in [ '.', '/' ] or path.find('/\.\./') != -1 or path[-1] == '/'):
                raise Exception('unacceptable path \'%s\'' % path)

            filename = join(self.url, path)[7:]
            if exists(filename):
                raise Exception('file (%s) already exists' % filename)

            if not exists(dirname(filename)):
                makedirs(dirname(filename))

            # write data
            self._write(fname, path, filename)


    def _log(self, message, t=datetime.utcnow()):
        if self.mode == 'w':
            with open("%slog" % self.url[7:], 'a') as logfile:
                t = datetime.utcnow()
                logfile.write(t.isoformat() + ' ' + message + '\n')
        else:
            Exception('package in read-only mode')


    def save(self):
        if self.mode in [ 'w', 'a' ]:
            with open(self.url[7:] + 'package.json', 'w') as out:
                out.write(str(self))
        else:
            Exception('package in read-only mode')


    def list(self):
        return list(self._desc['files'].keys())


    def finalize(self):
        if self.mode == 'r':
            raise Excpetion('package is in read-only mode')

        self._desc['status'] = 'finalized'
        self._log("FINALIZED")
        self.save()
        self.mode = 'r'


    def close(self):
        self.mode = 'r'


    def _add_directory(self, dir, path, exclude='^\\..*'):
        ep = compile(exclude)
        for f in listdir(dir):
            if not ep.match(f):
                self.add(sep.join([ dir, f ]), path=sep.join([ path, f ]), exclude=exclude)


    def _write(self, iname, path, oname):
        f = { '@id': path, 'urn': uuid4().urn, '@type': 'Resource' }
        h = md5()
        with open(iname, 'rb') as stream:
            with open(oname, 'wb') as out:
                data, length = None, 0

                while data != b'':
                    data = stream.read(10*1024)
                    out.write(data)
                    h.update(data)
                    size = out.tell()

        f['size'] = size
        f['checksum'] = 'MD5:' + h.hexdigest()
        self._desc['files'][path] = f

        with Magic(flags=MAGIC_MIME) as m:
            f['mime_type'] = m.id_filename(oname).split(';')[0]

        self._log('STORE %s size: %i, md5: %s' % (path, size, h.hexdigest()))
        self.save()


    def __iter__(self):
        return self.list()


    def __contains__(self, key):
        return key in self._desc['files']


    def __getitem__(self, key):
        return self._desc['files'][key]


    def __setitem__(self, key, value):
        self._desc['files'][key] = value


    def __str__(self):
        return dumps(self._desc, indent=4)

