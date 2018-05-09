#!/usr/bin/env python3

from starch import Archive,Package

archive = Archive()
patches = Archive()
ma = Archive(archive, extras=patches, base='https://example.net/')

key, p1 = archive.new()
urn = p1.description()['urn']
p1.add('README.md')
p1.finalize()
k2,p2 = patches.new(patches=urn)
p2.add('README.md')
k3,p3 = patches.new(patches=urn)
p3.add('server.py')
p3.add('README.md')
p3.tag('test:test')

print(archive.search({'patches': urn }))
print(patches.search({'patches': urn }))

print('KEY: ', key)
print('KEY: ', k2)
print('KEY: ', k3)

print(ma.get(key))

