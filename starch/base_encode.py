#!/usr/bin/env python

from io import StringIO
import urllib

def base_encode(n, base=u"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZbcdfghjklmnpqrstvwxz"):

    if n == 0:
        return base[0].encode('ascii')

    r = StringIO()
    while n:
        n, t = divmod(n, len(base))
        r.write(base[t])

    return r.getvalue().encode('ascii')[::-1]

