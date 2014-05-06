#!/usr/bin/env python

from StringIO import StringIO
from urllib2 import urlopen
from uuid import uuid4
from hashlib import md5,sha1

def mint_uuid():
    return uuid4().urn

class MemoryStore():
    def __init__(self, mint=mint_uuid):
        self.storage = {}
        self.mint = mint

    def store(self, data=None, uri=None, url=None, properties):
        assert url or data

        uri = uri or self.mint()
        data = data or urlopen(url).read()

        description['sha1'] = sha1(data).hexdigest()
        description['uri'] = uri

        self.storage[uri] = (description, data)

        return uri

    def get(self, uri):
        return (self.storage[uri][0], StringIO(self.storage[uri][1]))
    

