#!/usr/bin/env python3

from flask import Flask,request,render_template,Response,redirect,send_from_directory
from flask_cache import Cache
from requests import get
from json import loads,dumps
from yaml import load
from collections import OrderedDict
from starch import Package
from starch.utils import convert
from os.path import sep,exists,dirname,basename
from os import makedirs
from sys import stdout,stderr
from random import random
from shutil import rmtree
from datetime import datetime

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
cache = Cache(app, config={ 'CACHE_TYPE': 'simple' })
with open('config.yml') as f:
    config = load(f)


@app.route('/<id>/')
def package(id):
    return send_from_directory(directory(id), '_package.json', mimetype='application/json')


@app.route('/<id>/<path:path>', methods=[ 'GET', 'PUT', 'DELETE' ])
def package_file(id, path):
    p = Package(directory(id))

    return send_from_directory(directory(id), path, mimetype=p[path]['mime_type'])


@app.route('/_upload', methods=[ 'POST' ])
def upload():
    try:
        remove=True
        id = generate_id()
        d = directory(id)

        for file in request.files:
            path = sep.join([ directory(id), allowed(file) ])

            # @todo: this probably breaks with very large packages
            with open(path, mode='wb') as o:
                b=None
                while (b == None or b != b''):
                    b=request.files[file].read(100*1024)
                    o.write(b)

        # validate package
        try:
            Package(d).validate()
        except Exception as e:
            return str(e), 422

        # write ingest message in log
        with open(sep.join([ d, '_log' ]), mode='a') as f:
            f.write(datetime.utcnow().isoformat() + 'Z' + ' INGEST ' + id + '\n')

        remove=False
    finally:
        if remove and exists(d):
            try:
                rmtree(d)
            except Exception as e:
                print('warning: exception while deleting directory %s (%s)' % (d, str(e)))

    return redirect('/%s/' % id, code=302)


def generate_id():
    # @todo: obtain global lock
    id = convert(int(2**38*random()), radix=28, pad_to=8)
    while exists(directory(id)):
        print('warning: collision for id %s' % id, file=stderr)
        id = generate_id()

    makedirs(directory(id))

    return id


def directory(id):
    if '.' in id or '/' in id:
        raise Exception('not allowed characters in id \'%s\'')

    return sep.join([ config['archive']['root'] ] + [ id[2*i:2*i+2] for i in range(0,3) ] + [ id ]) + sep

def allowed(fname):
    if fname[:3] == '../' or '/../' in fname:
        raise Exception('not allowed characters in filename \'%s\'' % fname)

    return fname

if __name__ == "__main__":
    app.debug=True
    app.run(host='0.0.0.0')


