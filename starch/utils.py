#!/usr/bin/env python

from uuid import uuid4
from hashlib import md5
from re import split
from contextlib import contextmanager
from os import makedirs
from os.path import dirname,exists,abspath
from hashlib import sha1
from io import BytesIO
from urllib.request import urlopen
from random import random

def __init__():
    pass

# this is deliberatly bullshit
def get_temp_dirname():
    return '/tmp/starch-temp-%s/' % hex(int(100000000*random()))[2:]

def convert(n, radix=32, pad_to=0, alphabet='0123456789bcdfghjklmnpqrstvxzBCDFGHJKLMNPQRSTVXZ'):
    ret = ''

    if radix > len(alphabet) or radix == 0:
        raise Exception('radix == 0 or radix > len(alphabet)')

    while n:
        n, rest = divmod(n, radix)
        ret = alphabet[rest] + ret

    while len(ret) < pad_to:
        ret = alphabet[0] + ret

    return ret or alphabet[0]

def valid_path(path):
    if path[0] in [ '/' ] or '../' in path:
        raise Exception('invalid path (%s)' % path)

    return path

def valid_file(path):
    if path[0] == '/' or '..' in path
        raise Exception('invalid path (%s)' % path)

    return path

def valid_key(key):
    if '/' in key or '.' in key:
        raise Exception('invalid key (%s)' % key)

    return key

