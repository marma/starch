#!/usr/bin/env python

from uuid import uuid4
from hashlib import md5
from re import split
from contextlib import contextmanager
from os import makedirs
from os.path import dirname,exists
from hashlib import sha1
from io import BytesIO
from urllib2 import urlopen

def md5_pather(uri):
    hex = md5(uri).hexdigest()

    return [ '/'.join([ hex[ 2*i:2*i+2 ] for i in range(0,4) ] + [ hex ]), hex ]

def url_pather(uri):
    if uri[0:8] == 'urn:uuid':
        s = [ 'urn', 'uuid' ] + [ s[8:][ 2*i:2*i+2 ] for i in range(0,4) ] + [ s[8:] ]
    elif uri[0:7] == 'urn:nbn':
        hex = md5(uri).hexdigest()
        s = [ 'urn', 'nbn' ] + [ hex[ 2*i:2*i+2 ] for i in range(0,4) ] + [ hex ]
    elif uri[0:4] == 'http':
        s = [ x for x in split(':|/', uri) if x != '' ]

    if uri[-1] == '/':
        return [ '/'.join(s), '.content' ]
    else:
        return [ '/'.join(s[:-1]), s[-1] ]

def pairtree_pather(uri):
    pass

def uuid_minter():
    return uuid4().urn

def deny_overwrite(uri, path, old_meta, new_meta):
    raise Exception('overwrite not allowed')

@contextmanager
def closing(thing):
    try:
        yield thing
    finally:
        try:
            thing.close()
        except:
            pass

def write_file(file, stream):
    if not exists(dirname(file)):
        makedirs(dirname(file))

    # write data
    h = sha1()
    with open(file, 'w') as out:
        data, length = None, 0

        while data != '':
            data = stream.read(1024)
            out.write(data)
            h.update(data)
            size = out.tell()

    return 'sha1:' + h.hexdigest(), size


def get_property(g, s, p, default=None):
    for ret in g.objects(s,p):
        return str(ret)

    return default or None
