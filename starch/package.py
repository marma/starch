#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF,Literal,XSD,OWL
from os.path import exists,dirname,abspath,join,basename,isdir,join
from os import makedirs, walk, listdir, sep
from urllib2 import urlopen
from uuid import uuid4
from utils import random_slug,normalize_url
from contextlib import closing
from hashlib import md5,sha1
from random import random
from datetime import datetime
from io import BytesIO
from re import compile


class Package:
    def __init__(self, url, mode='r', uri=None, vocab=Namespace('http://example.org/vocab#'), plugins=[]):
        self.g = Graph()
        self.VOCAB = vocab
        self.DCTERMS = Namespace('http://purl.org/dc/terms/')
        self.mode = mode
        self.url = url = normalize_url(url)
        self.plugins = plugins

        self.protocol = url.split(':')[0]
        self.base = Namespace(dirname(url) + '/')

        self.g.bind('owl', OWL)

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
                    self.g.bind('dct', self.DCTERMS)
                    self.g.add((URIRef(self.base), RDF.type, self.VOCAB.Package))
                    self.g.add((URIRef(self.base), self.DCTERMS.created, Literal(t.isoformat() + 'Z', datatype=XSD.dateTime)))
                    self.g.add((URIRef(self.base), self.VOCAB.uri, URIRef(uri or uuid4().urn)))
                    self.g.add((URIRef(self.base), self.VOCAB.contains, URIRef(url)))
                    self.g.add((URIRef(self.base), self.VOCAB.describedby, URIRef(url)))
                    self.g.add((URIRef(url), RDF.type, self.VOCAB.Resource))
                    self.g.add((URIRef(url), self.DCTERMS.term('format'), Literal('text/turtle')))
                    self.g.add((URIRef(self.base), self.VOCAB.contains, URIRef(self.url + '-log')))
                    self.g.add((URIRef(self.url + '-log'), RDF.type, self.VOCAB.Log))

                    for plugin in plugins:
                        self.g.add((URIRef(self.base), self.VOCAB.plugin, Literal(plugin.__doc__)))

                    self._log("CREATED")

                    #self.save()
            else:
               raise Exception('write mode only supported for file URLs')
        elif self.mode == 'r':
            self.g.parse(url, format='turtle')

            if len([ x for x in self.g.subjects(RDF.type, self.VOCAB.Package) ]) != 1:
                raise Exception('number of packages in file != 1')
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


    def _add_directory(self, dir, path, store=True, exclude=[ '\\..*' ]):
        ep = [ compile(x) for x in exclude ]
        for f in listdir(dir):
            for p in ep:
                if not p.match(f):
                    print sep.join([ dir, f ]), sep.join([ path, f ])
                    self.add(sep.join([ dir, f ]), path=sep.join([ path, f ]), store=store, exclude=exclude)


    def add(self, url=None, path=None, data=None, store=True, traverse=True, exclude=[ '^\\..*' ]):
        assert store or not path
        assert data and store or url# and url.split(':')[0] in [ 'file', 'http', 'https' ]
        assert not path or path[1:] not in [ '.', '/' ]

        if self.mode is not 'w': raise Exception('package not writable')

        # make relative file URLs absolute
        if url and '://' not in url:
            url = 'file://' + abspath(url)

        # remove trailing / from path
        while path and path[-1:] == '/':
            path = path[:-1]

        # @todo: fix so that HTTP-URLs ending in '/' will get a better filename
        filename = join(self.basedir, path or (basename(url) if url else None) or str(urn))
        path = path or basename(filename)

        if traverse and url and url[:5] == 'file:' and isdir(url[7:]):
            self._add_directory(url[7:], path, store=store, exclude=[ '\\..*' ])
            return

        urn = uuid4()

        if store:
            if exists(filename):
                raise Exception('file (%s) already exists' % filename)

            if not exists(dirname(filename)):
                makedirs(dirname(filename))

            s = URIRef(self.base.term(path))
            self.g.add((URIRef(self.base), self.VOCAB.contains, s))

            # write data
            h = md5()
            with closing(urlopen(url)) if url else BytesIO(data) as stream:
                with open(filename, 'w') as out:
                    data, length = None, 0

                    while data != '':
                        data = stream.read(1024)
                        out.write(data)
                        h.update(data)
                        size = out.tell()

            self.g.add((s, RDF.type, self.VOCAB.Resource))
            self.g.add((s, self.VOCAB.path, Literal(path)))
            self.g.add((s, self.VOCAB.size, Literal(str(size))))
            self.g.add((s, self.VOCAB.md5, Literal(h.hexdigest())))
            self.g.add((s, OWL.sameAs, URIRef(urn.urn)))

            # run plugins and add triples
            for plugin in self.plugins:
                for p,o in plugin(self, filename):
                    self.g.add((s, p, o))

            self._log('STORE %s size: %i md5: %s' % (filename, size, h.hexdigest()))
        else:
            self._log('REF %s' % url)

        self.save()


    def _log(self, message, t=datetime.utcnow()):
        if self.mode == 'w':
            with open("%s-log" % self.url[7:], 'a') as logfile:
                t = datetime.utcnow()
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
        self._log("CLOSED")
        self.mode = 'r'


    def close(self):
        self.finalize()


    def __iter__(self):
        return self.list()


    def __str__(self):
        return self.serialize('turtle')
