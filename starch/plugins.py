#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF,Literal,XSD
from magic import Magic

def mime_type(p, filename):
    """starch.plugins.mime_type:0.1"""
    mime = Magic(mime=True)
    t = mime.from_file(filename)

    return [ (p.DCTERMS['format'], Literal(t)) ] if t else [ ]
