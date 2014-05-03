#!/usr/bin/env python

from os.path import abspath,dirname,exists,isfile,isdir
from os import makedirs,remove,rmdir,listdir
from datetime import datetime
from urllib2 import urlopen
from hashlib import sha1
from utils import md5_pather,url_pather,uuid_minter,deny_overwrite
from magic import Magic
from sys import argv,exit
from StringIO import StringIO
import json

class DiskStore:
    def __init__(self, basedir, pather=md5_pather, uri_minter=uuid_minter, overwrite_callback=None):
        self.base = abspath(basedir)
        self.base_data = self.base + '/data'
        self.pather = pather
        self.uri_minter = uri_minter
        self.overwrite_callback = overwrite_callback
        self.mime = Magic(mime=True)
        self.context = { 'content-type': 'http://purl.org/dc/terms/format', 'timestamp': 'http://purl.org/dc/terms/date' }

        if not exists(self.base):
            makedirs(self.base)

    def store(self, url=None, data=None, stream=None, uri=None, properties={}, force=False):
        assert bool(url) ^ bool(data)
        uri = uri or self.uri_minter()
        path = self.get_path(uri)
        file = '/'.join(path)
        meta = { '@context': self.context, '@id': uri, 'directory': path[1], 'filename': path[2] }
        meta.update(properties)

        if exists(file) and self.overwrite_callback and not force:
            old_meta = self.get(uri)[1]

            if not self.overwrite_callback(uri, path, meta, old_meta):
                return uri, path, old_meta

        self.__write_file(path, uri, meta, url=url, data=data)

        return uri, 'file://' + file, meta

    def __write_file(self, path, uri, meta, url=None, data=None):
        assert bool(url) ^ bool(data)
        directory = '/'.join(path[0:2])
        filename = path[2]
        file = '/'.join(path)
        t = datetime.utcnow()
        operation = 'STORE' if not exists(file) else 'UPDATE'
        meta['timestamp'] = t.isoformat()

        if not exists(directory):
            makedirs(directory)

        # write data
        req = StringIO(data) if data else urlopen(url)
        h = sha1()
        with open(file, 'w') as out:
            while data != '':
                data = req.read(1024)
                out.write(data)
                h.update(data)
                meta['content-length'] = out.tell()
        del req

        meta['sha1'] = h.hexdigest()

        # auto detect mime type?
        if 'content-type' not in meta:
            meta['content-type'] = self.mime.from_file(directory + '/' + filename)

        # write meta
        if not exists(directory + '/.meta'):
            makedirs(directory + '/.meta')

        with open(directory + '/.meta/' + filename, 'w') as out:
            out.write(json.dumps(meta))

        self.log('%s %s at %s, size:%d sha1:%s type:%s' % (operation, uri, '/'.join(path[1:]), meta['content-length'], meta['sha1'], meta['content-type']), t)

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
            return 'file://' + file, json.loads(m.read())

    def get_path(self, uri):
        return [ self.base_data ] + self.pather(uri)

    def log(self, message, t=datetime.utcnow()):
        with open("%s/log" % self.base, 'a+') as logfile:
            logfile.write(t.isoformat() + ' ' + message + '\n')

    def history(self, start=None):
        with open("%s/log" % self.base, 'rb') as logfile:
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

