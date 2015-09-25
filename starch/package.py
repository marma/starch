#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF,Literal,XSD
from os.path import exists,dirname,abspath,join
from os import makedirs
from urllib2 import urlopen
from uuid import uuid4
from utils import random_slug,normalize_url
from magic import Magic
from contextlib import closing
from hashlib import sha1
from random import random
from datetime import datetime
from io import BytesIO

DCTERMS = Namespace('http://purl.org/dc/terms/')

class Package:
    def __init__(self, url, mode='r', uri=None, vocab=Namespace('http://example.org/vocab#')):
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
            t = datetime.utcnow()

            if self.protocol == 'file':
                if exists(url[7:]):
                    raise Exception('package file (%s) already exists' % url[7:])
                else:
                    if exists(dirname(url[7:])):
                        raise Exception('directory (%s) already exists' % dirname(url[7:]))

                    if not exists(dirname(url[7:])):
                        makedirs(dirname(url[7:]))

                    self.g.bind('', self.VOCAB)
                    self.g.bind('dct', DCTERMS)
                    self.g.add((URIRef(self.base), RDF.type, self.VOCAB.Package))
                    self.g.add((URIRef(self.base), DCTERMS.created, Literal(t.isoformat() + 'Z', datatype=XSD.dateTime)))
                    self.g.add((URIRef(self.base), self.VOCAB.uri, URIRef(uri or uuid4().urn)))
                    self.g.add((URIRef(self.base), self.VOCAB.contains, URIRef(url)))
                    self.g.add((URIRef(self.base), self.VOCAB.describedby, URIRef(url)))
                    self.g.add((URIRef(url), RDF.type, self.VOCAB.Resource))
                    self.g.add((URIRef(url), DCTERMS.term('format'), Literal('text/turtle')))
                    self.g.add((URIRef(self.base), self.VOCAB.contains, URIRef(self.url + '-log')))
                    self.g.add((URIRef(self.url + '-log'), RDF.type, self.VOCAB.Log))

                    #self.save()
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
            for resource in self.g.objects(package, self.VOCAB.contains):
                yield str(resource)


    def get(self, res, pred):
        for o in self.g.objects(URIRef(res), URIRef(pred)):
            return str(o)

        return None


    def triples(self, res=None):
        return self.g.triples((URIRef(res) if res else None, None, None))


    def add(self, url=None, data=None, uri=None, filename=None, store=True):
        assert url or data
        assert (uri or url) or (data and store)

        if self.mode == 'w':
            filename = filename or random_slug()
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
                with closing(urlopen(url)) if url else BytesIO(data) as stream:
                    with open(path, 'w') as out:
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

                if uri:
                    self.g.add((s, self.VOCAB.uri, URIRef(uri)))
                elif url and url[:4] != 'file':
                    self.g.add((s, self.VOCAB.uri, URIRef(url)))

                # @TODO this should be a plugin instead
                if type.split('/')[0] == 'image':
                    try:
                        from PIL import Image
                        i = Image.open(path)
                        self.g.add((s, self.VOCAB.width, Literal(i.size[0])))
                        self.g.add((s, self.VOCAB.height, Literal(i.size[1])))
                    except:
                        self._log('WARNING image format not recognized (%s)' % filename)

                self._log('STORE %s size: %i type: %s sha1: %s' % (filename, size, type, h.hexdigest()))
            else:
                s = URIRef(uri or url)
                #self.g.add((s, RDF.type, self.VOCAB.Resource))
                self.g.add((URIRef(self.base), self.VOCAB.contains, s))
                self._log('REF %s' % s)

            #self.g.add((s, self.VOCAB.urn, URIRef(uuid4().urn)))

            self.save()
        else:
            raise Exception('package in read-only mode')


    def _log(self, message, t=datetime.utcnow()):
        if self.mode == 'w':
            with open("%s-log" % self.url[7:], 'a') as logfile:
                logfile.write(t.isoformat() + ' ' + message + '\n')
        else:
            Exception('package in read-only mode')


    def save(self):
        if self.mode == 'w':
            with open(self.url[7:], 'w') as out:
                out.write(str(self))
        else:
            Exception('package in read-only mode')


    def serialize(self, format='turtle'):
        assert format in ('trig', 'turtle', 'n3', 'json', 'mets')

        if format in ('trig', 'turtle', 'n3', 'json'):
            return self.g.serialize(base=self.base, format=format)
        elif format == 'mets':
            return None


    def finalize(self):
        self.save()
        self.mode = 'r'
        self._log("CLOSED")


    def __iter__(self):
        return self.list()


    def __str__(self):
        return self.serialize('turtle')

