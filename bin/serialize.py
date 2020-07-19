#!/usr/bin/env python3

from sys import argv,stderr,stdout,exit
from starch import Archive
from os import fdopen

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
    keys = argv[2:]

    size=0
    spinner=spinning_cursor()
    with fdopen(stdout.fileno(), "wb", closefd=False) as out, fdopen(stderr.fileno(), "wb", closefd=False) as err:
        for b in a.serialize(keys):
            size += len(b)
            err.write(f'\rCreating TAR-file ... ({sizeof_fmt(size)}) {next(spinner)}'.encode('utf-8'))
            out.write(b)

        err.write(f'\rCreating TAR-file ... ({sizeof_fmt(size)}) DONE!\n'.encode('utf-8'))

