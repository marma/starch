#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF
from memorystore import MemoryStore
from diskstore import DiskStore
from package import Package
from sys import argv
from utils import get_property,url_pather
import logging

DCTERMS = Namespace('http://purl.org/dc/terms/')

class Archive:
    def __init__(self, store=MemoryStore(), graph=Graph(), vocab=Namespace('http://example.org/vocab#')):
        self.store = store
        self.graph = graph
        self.vocab = vocab

    def __store(self, url=None, data=None, uri=None, properties={}):
        assert url or data
        return self.store.store(url=url, data=data, uri=uri, properties=properties)

    def ingest(self, url):
        p = Package(url, vocab=self.vocab)

        for res in p:
            mime = p.get(res, str(DCTERMS.term('format')))
            self.__store(res, uri=p.get(res, str(self.vocab.uri)), properties={ 'content-type': mime } if mime else {})


#        # find :Package and iterate over :Resources :contained within
#        for package in g.subjects(RDF.type, self.VOCAB.Package):
#            print package
#
#            for resource in g.objects(package, self.VOCAB.contains):
#                prop = {}
#                uri = get_property(g, resource, self.VOCAB.uri)
#                format = get_property(g, resource, URIRef('http://purl.org/dc/terms/format'))
#
#                if format:
#                    prop['content-type'] = format
#
#                self.store.store(url=resource, uri=uri, properties=prop)
#
#
#        """
#        # find all Resources in package and store them
#        for resource in g.subjects(RDF.type, self.VOCAB.Resource):
#            uri=None
#            for o in g.objects(resource, self.VOCAB.uri):
#                uri=o
#
#            describedByUri=None
#            for o in g.objects(resource, self.VOCAB.describedByUri):
#                describedByUri=o
#
#            prop = {}
#            for s,p,o in g.triples((resource, self.DCTERMS.format, None)):
#                prop['content-type'] = str(o)
#                print prop
#
#            desc = Graph()
#            for s,p,o in g.triples((resource, None, None)):
#                desc.add((uri,p,o))
#
#            self.store.store(url=str(resource), uri=str(uri))
#            self.store.store(data=desc.serialize(format='turtle'), uri=str(describedByUri), properties=prop)
#        """
if __name__ == "__main__":
    if len(argv) != 3:
        print "usage: %s <base> <package>" % argv[0]
        exit(1)

    logging.basicConfig()
    archive = Archive(store=DiskStore(argv[1], pather=url_pather))
    archive.ingest(argv[2])
