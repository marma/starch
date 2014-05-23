#!/usr/bin/env python

from StringIO import StringIO
from urllib2 import urlopen
from uuid import uuid4
from hashlib import md5,sha1
from utils import uuid_minter

class MemoryStore():
    def __init__(self, uri_minter=uuid_minter, overwrite_callback=None):
        self.storage = {}
        self.mint = uri_minter
        self.overwrite_callback=overwrite_callback

    def store(self, data=None, uri=None, url=None, properties={}):
        assert url or data

        uri = uri or self.mint()
        data = data or urlopen(url).read()

        description['sha1'] = sha1(data).hexdigest()
        description['uri'] = uri


        self.storage[uri] = (description, data)

        return uri

    def get(self, uri):
        return Resource(uri, self.storage[uri][0], data=self.storage[uri][1])
    

