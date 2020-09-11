from json import load,loads,dumps
from sys import stdin, stderr
from os import rename
from os.path import exists,join,basename,dirname,abspath
from urllib.parse import urljoin
from os import remove,makedirs,walk
from os.path import sep,getsize
from shutil import rmtree
from starch.utils import convert,timestamp,valid_path,valid_key,get_temp_dirname,dict_search,dict_values,TEMP_PREFIX
from random import random
from collections import Counter
from threading import RLock
from starch.result import create_result
from requests import get,head
import starch
from hashlib import md5,sha256
from copy import deepcopy
from queue import Queue
from threading import Thread
import tarfile
import datetime
from collections.abc import Iterator,Generator
from io import BytesIO
from tempfile import NamedTemporaryFile
from random import random
import shutil

MAX_ID=2**38

class FileArchive(starch.Archive):
    def __init__(self, root=None, base=None, relative_uris=False, index=None, mode='read-write', lockm=starch.LockManager(type='null'), **kwargs):
        self.temporary = root == None
        self.root_dir = root or get_temp_dirname()
        self.base = base if base and base[-1] == '/' else base + '/' if base else base # bass
        self.relative_uris = relative_uris or not base # omg
        self.mode = mode
        self.index = starch.Index(**index) if isinstance(index, dict) else index
        self.lockm = starch.LockManager(**lockm) if isinstance(lockm, dict) else lockm
        self.dir_split_strategy = kwargs.get('dir_split_strategy', 'hash')
        self.resolutions = kwargs.get('resolve', {})


    def new(self, key=None, **kwargs):
        self._check_mode()
        key = self._generate_key(suggest=valid_key(key) if key else None)

        #print(self.base)
        #print(key, flush=True)

        with self.lock(key):
            dir = self._directory(key)

            if exists(dir):
                raise Exception(f'key ({key}) already exists in archive')

            p = starch.Package(dir, mode='w', base=self.base + key + '/' if self.base else None, get_lock=self.lockm, **kwargs)
            p.callback = lambda msg, key=key, package=p, archive=self, **kwargs: archive._callback(msg, key=key, package=package)
            p.callback('new')

            self._log_add_package(key)

            return (key, p)
    

    def ingest(self, package, key=None, copy=True):
        def scrub_ids(x):
            x = deepcopy(x)
            x['@id'] = x['path']

            if copy and x['@type'] == 'Reference':
                x['@type'] = 'Resource'

                if 'url' in x:
                    del x['url']

            return x

        self._check_mode()
        key = self._generate_key(suggest=valid_key(key) if key else None)

        with self.lockm.get(key):
            dir = self._directory(key)
            makedirs(dir + sep)
    
            try:
                for path in package:
                    if package.get(path)['@type'] != 'Reference' or copy:
                        self._copy(package.get_raw(path), join(dir, valid_path(path)))

                with open(join(dir, '_package.json'), mode='w') as o:
                    d = deepcopy(package.description())
                    d['@id'] = ''
                    d['files'] = [ scrub_ids(x) for x in d['files'] ]
                    o.write(dumps(d, indent=2))

                # TODO copy meta-files too

                p = starch.Package(dir, base=self.base + key + '/' if self.base else None)
                p.validate()
            except Exception as e:  
                rmtree(dir)
                raise e

            self._log_add_package(key)
            self._callback('ingest', key=key, package=p)

            return key


    def patch(self, key, package):
        self._check_mode()

        with self.lockm.get(key):
            raise Exception('Not implemented')


    def get(self, key, mode='r'):
        if mode == 'w':
            raise Exception('mode \'w\' not allowed, use \'a\'')

        if mode == 'a' and self.mode == 'read-only':
            raise Exception('archive is read-only mode')

        d = self._directory(key)

        if exists(d):
            p=starch.Package(d, mode=mode, base=urljoin(self.base, key + '/') if self.base else None)
            p.callback=lambda msg, key=key, package=p, archive=self, **kwargs: archive._callback(msg, key=key, package=package)

            return p

        return None


    def delete(self, key, force=False):
        self._check_mode()

        if force:
            p = self.get(key, mode='a')

            if p:
                d = self._directory(key)
                rmtree(d)

                if self.index:
                    self.index.delete(key)

                return True
        else:
            raise Exception('Use the force (parameter)')


    def location(self, key, path=None):
        d = self._directory(valid_key(key))
        p = join(d, valid_path(path)) if path else d

        if exists(p):
            return 'file://' + p
        else:
            package = self.get(key)
            
            if package and path in package:
                f = package.get(path)

                if f['@type'] == 'Reference' and 'url' in f:
                    u = f['url']
                    scheme = u[:u.index(':')]

                    if scheme in self.resolutions:
                        u = 'file://' + self.resolutions[scheme] + u[u.index(':')+1:]

                    return u

        return None


    def serialize(self, key_or_iter, resolve=True, iter_content=False, buffer_size=100*1024, timeout=None, ignore=[]):
        def create_tar(f):
            #print(f'start create_tar', file=stderr)

            try:
                with tarfile.open(fileobj=f, mode="w|") as t:
                    for key in key_or_iter if isinstance(key_or_iter, (list, Iterator, Generator)) else [ key_or_iter ]:
                        checksums = {}
                        sizes = {}
                        resolved = set()

                        p = self.get(key)

                        if not p:
                            continue

                        for path in p:
                            if any([ fnmatch(path, p) for p in ignore ]):
                                continue

                            info = p[path]

                            if info['@type'] != 'Reference' or resolve:
                                ti = tarfile.TarInfo(f'{key}/{path}')
                                loc = self.location(key, path)

                                print(loc)

                                try:
                                    ti.mtime = int(datetime.fromisoformat(p.description()['created'][:-1]).timestamp())
                                except:
                                    ti.mtime = int(datetime.datetime.now().timestamp())                                

                                if loc.startswith('file:///'):
                                    sizes[path] = getsize(loc[7:])
                                    checksums[path] = info.get('checksum', 'SHA256:' + self._checksum(loc[7:]))
                                    ti.size = sizes[path]
                                    t.addfile(ti, self.open(key, path, mode='b'))
                                    resolved.add(path)
                                elif loc.startswith('http'):
                                    try:
                                        with NamedTemporaryFile(mode='w+b') as tempf, self.open(key, path, mode='rb') as pfile:
                                            h = sha256()
                                            data, length = None, 0

                                            while data != b'':
                                                data = pfile.read(100*1024)
                                                tempf.write(data)
                                                h.update(data)

                                            sizes[path] = tempf.tell()
                                            checksums[path] = 'SHA256:' + h.hexdigest()
                                            ti.size = sizes[path]

                                            tempf.seek(0)

                                            resolved.add(path)
                                            t.addfile(ti, tempf)
                                            resolved.add(path)
                                    except Exception as e:
                                        # ignore this file or reference
                                        #print(f'ignoring {key}/{key}: {e}', flush=True, file=stderr)
                                        ...
                                else:
                                    # ignore this reference
                                    #print(f'ignoring {key}/{key}', flush=True, file=stderr)
                                    ...

                        desc = load(open(self.location(key, '_package.json')[7:]))

                        for info in desc['files']:
                            path = info['path']

                            if path in resolved and info['@type'] == 'Reference':
                                info['@type'] = 'Resource'

                                if path in sizes:
                                    info['size'] = sizes[path]

                                if path in checksums:
                                    info['checksum'] = checksums[path]

                                if 'url' in info:
                                    del(info['url'])

                        desc['size'] = sum(sizes.values())

                        # add _package.json
                        b = dumps(desc, indent=4).encode('utf-8')
                        ti = tarfile.TarInfo(f'{key}/_package.json')
                        ti.size = len(b)

                        ti.mtime = int(datetime.datetime.now().timestamp())
                        t.addfile(ti, BytesIO(b))

            finally:
                f.close()
                #print(f'end create_tar', file=stderr)
 
        
        def get_iter(buffer_size=100*1024, timeout=None):
            q = Queue(10)
            f = starch.queueio.open(q, buffering=buffer_size, timeout=timeout)
            t = Thread(target=create_tar, args=(f,))
            t.start()

            try:
                x=q.get(timeout=timeout)
                while x != None:
                    if isinstance(x, BaseException):
                        raise x

                    yield x

                    x=q.get(timeout=timeout)
            finally:
                ...
                #f.close()

            t.join()


        def get_stream(buffer_size=100*1024, timeout=None):
            return starch.iterio.open(
                        get_iter(
                            buffer_size=buffer_size,
                            timeout=timeout),
                        mode='rb',
                        buffering=buffer_size)


        if iter_content:
            return get_iter(buffer_size=buffer_size, timeout=timeout)
        else:
            return get_stream(buffer_size=buffer_size, timeout=timeout)


    def deserialize(self, stream, key=None):
        self._check_mode()

        key = self._generate_key(suggest=valid_key(key) if key else None)

        with self.lock(key):
            dir = self._directory(key)

            if exists(dir):
                raise Exception(f'key ({key}) already exists in archive')

            basedir = dirname(abspath(dir))
            tmpdir = f'{basedir}/.ingest-{int(1000000*random())}'

            tkey=None
            t = tarfile.open(fileobj=stream, mode='r|')
            ti = t.next()
            while ti:
                if ti.name.startswith('/') or ti.name.startswith('..') or '/../' in ti.name:
                    raise Exception(f'path not allowed ({ti.name})')

                tkey = f'{basename(dirname(abspath(ti.name)))}'

                # TODO: deal with when keys differ in tar-file
                # TODO: deal with multiple packages in one tar-file

                t.extract(ti, path=tmpdir)
                ti=t.next()

            # move package to destination

            if tkey:
                rename(f'{tmpdir}/{key}', dir)
                shutil.rmtree(tmpdir)
                self._log_add_package(key)

            # rewrite @ids in content and structure files
            p = self.get(key, mode='a')
            for path in p:
                if p[path].get('@type', None) in [ 'Content', 'Structure' ]:
                    #print(path)
                    j = load(self.open(key, path))
                    p.add(path=path, data=self._replace_ids(j, key=key), replace=True)

        return key


    def exists(self, key, path=None):
        #d = self._directory(valid_key(key))
        l = self.location(valid_key(key), path=valid_path(path) if path else None)

        if l:
            return exists(l[7:])

        #if path:
        #    return exists(join(d, valid_path(path)))
        #else:
        #    return exists(d)

        return False


    def open(self, key, path, mode=''):
        loc = self.location(key, path)

        if loc[:7] == 'file://':
            return open(loc[7:], mode='r'+mode)
        elif loc[:4] == 'http':
            # @TODO Check credentials
            r = get(loc, stream=True)

            # maybe wrap this to avoid credentials leak?
            return r.raw

        return None


    def read(self, key, path, mode=''):
        with self.open(key, path, mode=mode) as f:
            return f.read()


    def description(self, key):
        ...

    #def iter(self, path, chunk_size=10*1024, range=None):
    #    ...

    def search(self, query, start=0, max=None, sort=None):
        # This is deliberatly non-optimal for small
        # resultsets in large archives and/or paging.
        # Use an index and the web frontend instead

        if self.index:
            return self.index.search(query, start, max, sort)

        hits = [ x for x in self._search_iterator(query, start, max, sort) ]
        max = max or len(hits)

        if start >= len(hits):
            return (start, 0, len(hits), iter([]))

        key_iter = iter(hits[start:start + max])

        return create_result(
                    start=start,
                    n=min(max, len(hits), len(hits) - start),
                    m=len(hits),
                    key_iter=key_iter,
                    archive=self)


    def count(self, query, cats={}):
        if self.index:
            return self.index.count(query, cats)

        ret = { k:Counter() for k in cats }

        for key, package in self.search(query):
            for key in cats:
                ret[key].update(dict_values(package.description(), cats[key]))
            
        return ret


    def lock(self, key):
        return self.lockm.get(key)


    def _search_iterator(self, query, start=0, max=None, sort=None):
        for key, package in self.items():
            if dict_search(query, package.description()):
                yield key


    def _directory(self, key):
        h = md5()
        h.update(key.encode('utf-8'))     

        if self.dir_split_strategy == 'hash':
            return join(self.root_dir, *[ h.hexdigest()[2*i:2*i+2] for i in range(0,3) ], key)
        elif self.dir_split_strategy == 'split':
            return join(self.root_dir, *[ key[2*i:2*i+2] for i in range(0,3) ], key)
        else:
            raise Exception(f'No such split strategy ("{self.dir_split_strategy}")')


    def _create_directory(self, key):
        self._check_mode()
        dir = self._directory(key)
        makedirs(dir + '/')

        return dir


    def _generate_key(self, suggest=None):
        self._check_mode()
        # @TODO: locking a central function and waiting for I/O, that
        # might take a long time to return, is non-optimal
        with self.lockm.get('keygen'):
            key = suggest or convert(int(MAX_ID*random()), radix=28, pad_to=8)

            if exists(self._directory(key)):
                if suggest:
                    raise Exception('key %s already exists')

                self._log('warning: collision for key %s' % key)

                return self._generate_key()

            return key


    def keys(self):
        if exists(join(self.root_dir, 'packages')):
            with open(join(self.root_dir, 'packages')) as f:
                for line in f:
                    # prevent potential half-written last id from being returned
                    if line[-1] == '\n':
                        yield line[:-1]
        else:
            return iter([])


    def items(self):
        for key in self:
            yield (key, self.get(key))


    def __iter__(self):
        yield from self.keys()


    def _check_mode(self):
        if self.mode == 'read-only':
            raise Exception('archive in read-only mode')


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
                #print(self.get(key))
                #print(self.base)
                #print('index %s' % key, flush=True)
                self.index.update(key, package or self.get(key))


    def __del__(self):
        if self.temporary and self.root_dir.startswith(TEMP_PREFIX):
            if  exists(self.root_dir):
                rmtree(self.root_dir)

            if self.index:
                self.index.destroy()

    def __str__(self):
        return repr([ self.root_dir, self.temporary, self.index, self.lockm ])


    def __getitem__(self, key):
        return self.get(key)

    
    def __contains__(self, key):
        return exists(self._directory(key))


    def _checksum(self, loc):
        with open(loc, mode='rb') as pfile:
            h = sha256()
            data, length = None, 0

            while data != b'':
                data = pfile.read(100*1024)
                h.update(data)

            return h.hexdigest()


    def _replace_ids(self, j, key):
        def _sub(v):
            if v.startswith('http'):
                if self.relative_uris:
                    i = v.split(key)[1]
                    return i if i[0] != '/' else i[1:]
                else:
                    return f'{self.base}{key}{v.split(key)[1]}'
            else:
                if self.relative_uris:
                    return v
                else:
                    return f'{self.base}{key}{v if v[0] == "#" else ("/" + v)}'


        def _handle(k,v):
            #print('handle', k)
            if k == '@id':
                return _sub(v)
            elif k == 'has_part':
                return [ self._replace_ids(x, key) for x in v ]
            elif k == 'has_representation':
                return [ _sub(x) for x in v ]

            return v


        if isinstance(j, list):
            return [ self._replace_ids(x, key) for x in j ]
        elif isinstance(j, dict):
            return { k:_handle(k,v) for k,v in j.items() }

        return j

