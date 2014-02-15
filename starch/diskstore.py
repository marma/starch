#!/usr/bin/env python

import hashlib
import uuid
import sys
from os.path import abspath,dirname,exists,isfile,isdir
from os import getpid,makedirs
import datetime
from urllib2 import urlopen
from rdflib import Graph()

class DiskStore:
    def __init__(self, basedir):
        self.basedir = abspath(basedir)

        if not exists(basedir):
            makedirs(self.basedir)

    def log(self, message, t=datetime.datetime.utcnow()):
        with open("%s/log" % self.basedir, 'a+') as logfile:
            logfile.write(t.isoformat() + ' ' + message + '\n')

    def store(self, url, description=Graph()):
        u = uuid.uuid4()
        apath = self.basedir + '/data/' + '/'.join([ u.hex[2*i:2*i+2] for i in range(0,4) ] + [ u.hex ])
        makedirs(apath)

        req = urlopen(url)
        d = hashlib.sha1()
        size = 0
        with open(apath + '/content', 'w') as out:
            while True:
                data = req.read(1024)
                size += len(data)
                    
                if data == '':
                    break

                out.write(data)
                d.update(data)

        meta['urn'] = u.urn
        meta['sha1'] = d.hexdigest()
        meta['size'] = size
        
        if 'Content-type' in req.headers:
            meta['format'] = req.headers['Content-type']

        if 'Content-disposition' in req.headers:
            meta['filename'] = req.headers['Content-disposition']

        if url.split(':')[0] == 'file':
            meta['filename'] = url.split(':')[1].split('/')[-1:][0]
        
        meta['original_url'] = url

        t = datetime.datetime.utcnow()
        meta['timestamp'] = datetime.datetime.utcnow().isoformat()

        with open(apath + '/meta', 'w') as metaf:
            metaf.write(repr(meta))

        self.log('store %s size:%d sha1:%s' % (u.hex, size, d.hexdigest()), t)

        return u


    def get(self, urn):
        base = self.basedir + '/data/' + '/'.join([ urn.hex[2*i:2*i+2] for i in range(0,4) ] + [ urn.hex ])
 
        with open(base + '/meta') as m:
            return base + '/content', eval(m.read())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print "usage: %s <base directory> <URL>" % sys.argv[0]
        sys.exit(1)

    ds = DiskStorage(sys.argv[1])
    u = ds.store(sys.argv[2])

    print ds.get(u)

