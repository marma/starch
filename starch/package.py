#!/usr/bin/env python

from rdflib import Graph,Namespace

class Package:
    def __init__(self, url, vocab=Namespace('http://example.org/vocab#')):
        self.graph = Graph()
        self.graph.parse(url, format='turtle')
        self.VOCAB = vocab

    def list(self):
        for package in g.subjects(RDF.type, self.VOCAB.Package):
            for resource in self.graph.objects(package, self.VOCAB.contains):
                yield str(resource)
