#!/usr/bin/env python3

from starch import Archive,Package

archive = Archive()
patches = Archive()
ma = Archive(archive, extras=patches, base='https://example.net/')

key, p1 = archive.new()
p1.add('README.md')
p1.finalize()
p2 = patches.new(patches=p1.description()['urn'])[1]
p2.add('README.md')
p3 = patches.new(patches=p1.description()['urn'])[1]
p3.add('test.py')
p3.add('README.md')

print(p1)
print(p2)
print(p3)

print(ma.get(key))

