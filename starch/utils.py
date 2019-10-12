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
from datetime import datetime
from re import match
from copy import deepcopy
from collections import Counter
from sys import stderr

from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter#process_pdf
from pdfminer.pdfpage import PDFPage
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from io import StringIO

TEMP_PREFIX='/tmp/starch-temp-'

def __init__():
    pass

class HttpNotFoundException(Exception):
    pass


def get_temp_dirname():
    return TEMP_PREFIX + '%s/' % uuid4()


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
    if path[0] == '/' or '..' in path:
        raise Exception('invalid path (%s)' % path)

    return path


def valid_key(key):
    if '/' in key or '.' in key:
        raise Exception('invalid key (%s)' % key)

    return key


def timestamp():
    return datetime.utcnow().isoformat() + 'Z'


def dict_search(a, b):
    if isinstance(a, (str, int, float)):
        if isinstance(b, (str, int, float)):
            return a == b
        elif isinstance(b, (list, iter)):
            return any([ dict_search(a, x) for x in b ])
    elif isinstance(a, dict) and isinstance(b, dict):
        if set(a).issubset(b):
            return all([ dict_search(a[key], b[key]) for key in a ])

    return False


def wildcard_match(a, b):
    return a == b or a == '*'


def dict_values(d, path):
    p,di = [], deepcopy(path)

    while isinstance(di, dict):
        p += [ next(iter(di.keys())) ]
        di = next(iter(di.values()))

    p += [ di ]

    return _dict_values(d, p)


def _dict_values(d, path):
    if path == []:
        if isinstance(d, list):
            return Counter([ x for x in d if not isinstance(x, (list, dict, tuple)) ])
        elif not isinstance(d, (list, dict, tuple)):
            return Counter([d])
    else:
        if isinstance(d, (list, tuple)):
            s=Counter()
            for x in d:
                s.update(_dict_values(x, path))
            return s
        elif isinstance(d, dict) and path[0] in d:
            return _dict_values(d[path[0]], path[1:])
    
    return Counter()


def chunked(f, chunk_size=100*1024, max=None):
    pos,b = 0,None
    while b != b'' and b != '':
        b = f.read(chunk_size if not max else min(chunk_size, max - pos))
        #print('chunk %d' % len(b), file=stderr, flush=True)
        pos += len(b)

        if b != b'' and b != '':
            yield b


def decode_range(srange):
    s = match('bytes=(\\d+)-(\\d*)', srange).groups()

    return ( int(s[0]), int(s[1]) if s[1] != '' else None )


@contextmanager
def nullctxmgr():
    yield


def nullcallback(msg, **kwargs):
    #print(msg, kwargs)

    if msg == 'lock':
        return nullctxmgr()


def rebase(desc, base, index_base, in_place=False):
    if base or index_base:
        ret = deepcopy(desc) if in_place else desc
        ret['@id'] = rebase_uri(['@id'], base, index_base)

        for f in ret['files']:
            f['@id'] = rebase_uri(f['@id'])

        return ret
    else:
        return desc


def rebase_uri(u, base, index_base):
    return (base or '') + (u[len(index_base):] if index_base else u)

def max_iter(i, max):
    n=0
    for chunk in i:
        if len(chunk) + n < max:
            yield chunk
            n += len(chunk)
        else:
            yield chunk[:max-n]

            return


def pdf_to_textarray(stream):
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    codec = 'utf-8'

    ret = []
    for page in PDFPage.get_pages(stream):
        with StringIO() as sio, TextConverter(rsrcmgr, sio, codec=codec, laparams=laparams) as device:
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            interpreter.process_page(page)
            ret += [ sio.getvalue() ]

    return ret


def guess_content(path):
    if path.endswith('.jpg'):
        return 'image/jpeg'
    elif path.endswith('.jp2'):
        return 'image/jp2'
    elif path.endswith('.json'):
        return 'application/json'
    elif path.endswith('.pdf'):
        return 'application/pdf'
    elif path.endswith('.xml'):
        return 'text/xml'
    elif path.endswith('.metadata'):
        return 'text/xml'
    
    return 'application/octet-stream'






