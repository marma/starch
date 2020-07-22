#!/usr/bin/env python3

from sys import argv,stderr,stdout,exit
from os import fdopen
import os
import sys

PACKAGE_PARENT = '..'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))

from starch import Archive

def spinning_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor

def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

if __name__ == "__main__":
    if len(argv) < 3:
        print(f'usage: {argv[0]} <path> <key> [key key ... key]')
        exit(1)

    a = Archive(argv[1])
    keys = argv[2:] if len(argv) > 3 else argv[2]

    size=0
    spinner=spinning_cursor()
    with fdopen(stdout.fileno(), "wb", closefd=False) as out, fdopen(stderr.fileno(), "wb", closefd=False) as err:
        with a.serialize(keys, buffer_size=1024*1024) as tarout:
            b = tarout.read(1024*1024)
            while b != b'':
                size += len(b)
                #err.write(f'got {len(b)} bytes\n'.encode('utf-8'))
                err.write(f'\rStreaming TAR-file ... ({sizeof_fmt(size)}) {next(spinner)}     '.encode('utf-8'))
                err.flush()
                out.write(b)
                b = tarout.read(1024*1024)


        #for b in a.serialize(keys, buffer_size=1024*1024, iter_content=True):
        #    size += len(b)
        #    #err.write(f'got {len(b)} bytes\n'.encode('utf-8'))
        #    err.write(f'\rStreaming TAR-file ... ({sizeof_fmt(size)}) {next(spinner)}     '.encode('utf-8'), flush=True)
        #    out.write(b)

        err.write(f'\rStreaming TAR-file ... ({sizeof_fmt(size)}) DONE!    \n'.encode('utf-8'))

