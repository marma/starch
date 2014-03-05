#!/usr/bin/env python

from rdflib import Graph,Namespace
from starch.store import MemoryStore

class Archive:
    def __init__(self, store=MemoryStore(), graph_store=Graph(), vocab=Namespace('http://example.org/vocab#'), types=Namespace('http://example.org/type#', package_uri=types.Package, resource_uri=types.Resource):
        self.store = store
        self.gstore = graph_store
        self.VOCAB = vocab
        self.TYPES = types
        self.package_uri = package_uri
        self.resource_uri = resource_uri

    def store(self, url, description):
        self.store.store(url, description)

    def ingest(self, url):
        g = Graph()
        g.parse(url, format='turtle')

        self.store(None, g)
        self.gstore.add(g)

        # find all Resources in package and store them
        for uri in g.subjects(RDF.type, self.TYPES.Resource):
            desc = g.triples(uri, None, None)
            self.store(uri, desc)
            self.gstore.store(desc)

