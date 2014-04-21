#!/usr/bin/env python

from os.path import abspath,dirname,exists,isfile,isdir
from os import makedirs
from datetime import datetime
from urllib2 import urlopen
from hashlib import sha1
from utils import md5_pather,url_pather,uuid_minter
from magic import Magic
from sys import argv,exit

class DiskStore:
    def __init__(self, basedir, pather=md5_pather, uri_minter=uuid_minter, overwrite_callback=None):
        self.base = abspath(basedir)
        self.pather = pather
        self.uri_minter = uri_minter
        self.overwrite_callback = overwrite_callback
        self.mime = Magic(mime=True)

        if not exists(self.base):
            makedirs(self.base)

    def log(self, message, t=datetime.utcnow()):
        with open("%s/log" % self.base, 'a+') as logfile:
            logfile.write(t.isoformat() + ' ' + message + '\n')

    def store(self, url=None, data=None, uri=None, properties={}, force=False):
        assert bool(url) ^ bool(data)
        uri = uri or self.uri_minter()
        path = [ self.base + '/data' ] + self.pather(uri)
        meta = { 'uri': uri, 'directory': path[1], 'filename': path[2], 'properties': properties }
        
        if exists('/'.join(path)) and self.overwrite_callback and not force:
            old_meta = get(uri)[1]

            if not self.overwrite_callback(uri, path, meta, old_meta):
                return uri, path, old_meta

        self.write_file(path, uri, meta, url=url, data=data)

        return uri, '/'.join(path), meta

    def write_file(self, path, uri, meta, url=None, data=None):
        assert bool(url) ^ bool(data)
        directory = path[0] + '/' + path[1]
        filename = path[2]
        t = datetime.utcnow()
        meta['timestamp'] = t.isoformat()

        if not exists(directory):
            makedirs(directory)

        # write data
        if data:
            meta['sha1'] = sha1(data).hexdigest()
            meta['content-type'] = self.mime.from_buffer(data)

            with open(directory + '/' + filename, 'w') as out:
                out.write(data)
                meta['content-length'] = out.tell()
        else:
            req = urlopen(url)
            h = sha1()
            with open(directory + '/' + filename, 'w') as out:
                while data != '':
                    data = req.read(1024)
                    out.write(data)
                    h.update(data)
                    meta['content-length'] = out.tell()
            del req

            meta['sha1'] = h.hexdigest()
            meta['content-type'] = self.mime.from_file(directory + '/' + filename)

        # override mime type?
        if 'content-type' in meta['properties'].keys():
            meta['content-type'] = meta['properties']['content-type']

        # write meta
        if not exists(directory + '/.meta'):
            makedirs(directory + '/.meta')

        with open(directory + '/.meta/' + filename, 'w') as out:
            out.write(str(meta))

        self.log('STORE: %s at %s, size:%d sha1:%s type:%s' % (uri, '/'.join(path[1:]), meta['content-length'], meta['sha1'], meta['content-type']), t)

    def get(self, urn):
        base = self.basedir + '/data/' + '/'.join([ urn.hex[2*i:2*i+2] for i in range(0,4) ] + [ urn.hex ])
 
        with open(base + '/meta') as m:
            return base + '/content', eval(m.read())


if __name__ == "__main__":
    if len(argv) < 3 or len(argv) > 4:
        print "usage: %s <base directory> <URL> [URI]" % argv[0]
        exit(1)
    
    uri = argv[3] if len(argv) == 4 else None
    ds = DiskStore(argv[1], pather=url_pather)
    
    print ds.store(argv[2], uri=uri)

