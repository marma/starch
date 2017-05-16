#!/usr/bin/env python

from rdflib import Graph,Namespace,URIRef,RDF,Literal,XSD
from magic import Magic,MAGIC_MIME,MAGIC_RAW
from PIL import Image

def mime_type(p, filename, path):
    """starch.plugins.mime_type:0.1"""
    ret = []

    with Magic(flags=MAGIC_MIME) as m:
        ret += [ (p.DCTERMS['format'], Literal(m.id_filename(filename))) ]

    with Magic(flags=MAGIC_RAW) as m:
        ret += [ (p.DCTERMS['format'], Literal(m.id_filename(filename))) ]

    return ret

def image_properties(p, filename, path):
    """starch.plugins.image_properties:0.1"""
    ret = []

    try:
        i = Image.open(filename)
        ret += [ (p.VOCAB.width, Literal(i.width)) ]
        ret += [ (p.VOCAB.height, Literal(i.height)) ]
    except:
        pass
        #p._log('WARNING image format not recognized (%s)' % path)

    return ret
