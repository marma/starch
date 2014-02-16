#!/usr/bin/env python

from rdflib import Graph,Namespace

class Archive:
    def __init__(self, _store, _gstore, _default_ns):
        self.store = _store
        self.gstore = _gstore
        self.STARCH_NS = _default_ns

    def store(self, url, description):
        self.store.store(url, description)

    def ingest(self, url):
        g = Graph()
        g.parse(url, format='turtle')

        self.store(None, g)
        self.gstore.add(g)

        # find all Resources in package and store them
        for uri in g.subjects(RDF.type, self.STARCH_NS.Resource):
            desc = g.triples(uri, None, None)
            self.store(uri, desc)
            self.gstore.store(desc)

