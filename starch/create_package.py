#!/usr/bin/env python

from package import Package
from plugins import mime_type
from sys import argv

if __name__ == "__main__":
    p = Package(argv[1] + '/package.ttl', mode='w', plugins=[ mime_type ])
    
    for f in argv[2:]:
        p.add(f)

    p.close()
