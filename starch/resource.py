#!/usr/bin/env python

from urllib2 import urlopen
from utils import closing
from io import BytesIO

class Resource:
    def __init__(self, uri, meta, url=None, data=None):
        assert url or data
        self.uri = uri
        self.meta = meta
        self.url = url
        self.data = data

    def data(self):
        return data or urlopen(url).read()

    def stream(self):
        return closing(BytesIO(data)) if data else closing(urlopen(url))

