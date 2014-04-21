#!/usr/bin/env python

from uuid import uuid4
from hashlib import md5

def md5_pather(uri):
    hex = md5(uri).hexdigest()

    return [ '/'.join([ hex[2*i:2*i+2] for i in range(0,4) ] + [ hex ]), hex ]

def uuid_minter():
    return uuid4().urn
