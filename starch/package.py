#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF,Literal
from os.path import exists,dirname,abspath,join
from os import makedirs
from urllib2 import urlopen
from uuid import uuid4
#from utils import random_slug
from magic import Magic
from contextlib import closing
from hashlib import sha1
from random import random

DCTERMS = Namespace('http://purl.org/dc/terms/')

def normalize_url(url):
    if url.find(':') != -1:
        if url.split(':')[0] not in [ 'file', 'http', 'https', 'ftp' ]:
            raise Exception('unsupported protocol')

        if 'file:///' in url:
            return url
        elif 'file:' in url:
            return 'file://' + abspath(url[5:])
        else:
            return url
    else:
        return 'file://' + abspath(url)


def random_slug():
    return sha1(str(random())).hexdigest()


class Package:
    def __init__(self, url, mode='r', vocab=Namespace('http://example.org/vocab#')):
        self.g = Graph()
        self.VOCAB = vocab
        self.mode = mode
        self.url = url = normalize_url(url)
        self.mime = Magic(mime=True)

        self.protocol = url.split(':')[0]
        self.base = Namespace(dirname(url) + '/')

        if self.protocol == 'file':
            self.basedir = dirname(url[7:])

        # check
        if self.mode == 'w':
            if self.protocol == 'file':
                if exists(url[7:]):
                    raise Exception('package file (%s) already exists' % url[7:])
                else:
                    #if exists(dirname(url[7:])):
                    #    raise Exception('directory (%s) already exists' % dirname(url[7:]))

                    if not exists(dirname(url[7:])):
                        makedirs(dirname(url[7:]))

                    self.g.bind('', self.VOCAB)
                    self.g.bind('dct', DCTERMS)
                    self.g.add((URIRef(self.base), RDF.type, self.VOCAB.Package))
                    self.g.add((URIRef(self.base), self.VOCAB.urn, URIRef(uuid4().urn)))
                    self.g.add((URIRef(self.base), self.VOCAB.contains, URIRef(url)))
                    self.g.add((URIRef(self.base), self.VOCAB.describedby, URIRef(url)))
                    self.g.add((URIRef(url), RDF.type, self.VOCAB.Resource))
                    self.g.add((URIRef(url), DCTERMS.term('format'), Literal('text/turtle')))


                    self.save()
            else:
               raise Exception('write mode only supported for file URLs')
        elif self.mode == 'r':
            self.g.parse(url, format='turtle')

            if len([ x for x in self.g.subjects(RDF.type, self.VOCAB.Package) ]) != 1:
                raise Exception('Number of packages in file != 1')
        else:
            raise Exception('unsupported mode (\'%s\')' % mode)


    def list(self):
        for package in self.g.subjects(RDF.type, self.VOCAB.Package):
            print package

            for resource in self.graph.objects(package, self.VOCAB.contains):
                print resource
                yield str(resource)


    def add(self, url, uri=None, filename=random_slug(), store=True):
        if self.mode == 'w':
            path = join(self.basedir, filename)

            if exists(path):
                raise Exception('file (%s) already exists' % path)

            if not exists(dirname(path)):
                makedirs(dirname(path))

            if store:
                s = URIRef(self.base.term(filename))
                self.g.add((URIRef(self.base), self.VOCAB.contains, s))

                # write data
                h = sha1()
                with open(path, 'w') as out, closing(urlopen(url)) as stream:
                    data, length = None, 0

                    while data != '':
                        data = stream.read(1024)
                        out.write(data)
                        h.update(data)
                        size = out.tell()

                type = self.mime.from_file(path)
                self.g.add((s, RDF.type, self.VOCAB.Resource))
                self.g.add((s, DCTERMS.term('format'), Literal(type)))
                self.g.add((s, self.VOCAB.size, Literal(str(size))))
                self.g.add((s, self.VOCAB.sha1, Literal(h.hexdigest())))
            else:
                s = uri or url
                self.g.add((s, RDF.type, self.VOCAB.Resource))
                self.g.add((URIRef(self.base), self.VOCAB.contains, s))

            if uri:
                self.g.add((s, self.VOCAB.uri, URIRef(uri)))
            elif url[:4] != 'file':
                self.g.add((s, self.VOCAB.uri, URIRef(url)))
            else:
                self.g.add((s, self.VOCAB.uri, URIRef(uuid4().urn)))

            self.save()
        else:
            raise Exception('package in read-only mode')


    def save(self):
        if self.mode == 'w':
            with open(self.url[7:], 'w') as out:
                out.write(str(self))
        else:
            Exception('package in read-only mode')


    def __str__(self):
        return self.g.serialize(base=self.base, format='turtle')

