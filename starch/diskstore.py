#!/usr/bin/env python

from os.path import abspath,dirname,exists,isfile,isdir
from os import makedirs,remove,rmdir,listdir
from datetime import datetime
from urllib2 import urlopen
from utils import md5_pather,url_pather,uuid_minter,deny_overwrite,closing,write_file
from magic import Magic
from sys import argv,exit
from StringIO import StringIO
import json
from resource import Resource

class DiskStore:
    def __init__(self, basedir, pather=md5_pather, uri_minter=uuid_minter, overwrite_callback=None):
        self.base = abspath(basedir)
        self.base_data = self.base + '/data'
        self.pather = pather
        self.mint = uri_minter
        self.overwrite_callback = overwrite_callback
        self.mime = Magic(mime=True)
        self.context = { 'content-type': 'http://purl.org/dc/terms/format', 'timestamp': 'http://purl.org/dc/terms/date' }

        if not exists(self.base):
            makedirs(self.base)

    def store(self, url=None, data=None, stream=None, uri=None, properties={}, force=False, write_file=write_file):
        assert url or data or stream
        uri = uri or self.mint()
        path = self.get_path(uri)
        directory = '/'.join(path[0:2])
        filename = path[2]
        file = '/'.join(path)
        meta = { '@context': self.context, '@id': uri, 'directory': path[1], 'filename': path[2] }
        t = datetime.utcnow()

        operation = 'STORE' if not exists(file) else 'UPDATE'
        meta['timestamp'] = t.isoformat()
        meta.update(properties)

        if exists(file) and self.overwrite_callback and not force:
            return self.overwrite_callback(uri, path, meta, self.get(uri).meta)

        # write file
        with closing(StringIO(data)) if data else stream or closing(urlopen(url)) as f:
            meta['checksum'], meta['content-length'] = write_file(file, f)

        # auto detect mime type?
        if 'content-type' not in meta:
            meta['content-type'] = self.mime.from_file(file)

        # write meta
        write_file(directory + '/.meta/' + filename, StringIO(json.dumps(meta)))

        self.log('%s %s at %s, size:%d, %s type:%s' % (operation, uri, '/'.join(path[1:]), meta['content-length'], meta['checksum'], meta['content-type']), t)

        return Resource(uri, meta, url='file://' + file)

    def delete(self, uri):
        path = self.get_path(uri)
        dir, file = '/'.join(path[0:2]), '/'.join(path)
        self.log('DELETE: %s at %s' % (uri, file))

        remove(file)
        remove('/'.join(path[0:2]) + '/.meta/' + path[2])

        if len(listdir(dir + '/.meta/')) == 0:
            rmdir(dir + '/.meta/')

        while dir != self.base_data and len(listdir(dir)) == 0:
            rmdir(dir)
            dir = '/'.join(dir.split('/')[:-1])

        return dir, file

    def get(self, uri):
        path = self.get_path(uri)
        file = '/'.join(path)

        with open('/'.join(path[0:2]) + '/.meta/' + path[2]) as m:
            return Resource(uri, json.loads(m.read()), url='file://')

    def get_path(self, uri):
        return [ self.base_data ] + self.pather(uri)

    def log(self, message, t=datetime.utcnow()):
        with open("%s/log" % self.base, 'a+') as logfile:
            logfile.write(t.isoformat() + ' ' + message + '\n')

    # @todo fix naive implementation of start
    def history(self, start=None):
        with open("%s/log" % self.base, 'r') as logfile:
            for line in logfile:
                if line[0:26] > start:
                    yield line.split()[0:3]

if __name__ == "__main__":
    if len(argv) < 3:
        print "usage: %s <base directory> <operation> [options]" % argv[0]
        exit(1)

    ds = DiskStore(argv[1], pather=url_pather)#, overwrite_callback=deny_overwrite)

    if argv[2] == 'store':
        uri = argv[4] if len(argv) == 5 else None
        print ds.store(argv[3], uri=uri)
    elif argv[2] == 'get':
        print ds.get(argv[3])
    elif argv[2] == 'delete':
        print ds.delete(argv[3])
    elif argv[2] == 'history':
        for item in ds.history(start=None if len(argv) == 3 else argv[3]):
            print item

