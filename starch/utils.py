#!/usr/bin/env python

from uuid import uuid4
from hashlib import md5
from re import split

def md5_pather(uri):
    hex = md5(uri).hexdigest()

    return [ '/'.join([ hex[ 2*i:2*i+2 ] for i in range(0,4) ] + [ hex ]), hex ]

def url_pather(uri):
    s = [ x for x in split(':|/', uri) if x != '' ]
    
    if uri[-1] == '/':
        return [ '/'.join(s), '.content' ]
    else:
        return [ '/'.join(s[:-1]), s[-1] ]

def pairtree_pather(uri):
    pass

def uuid_minter():
    return uuid4().urn

