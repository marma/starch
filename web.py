#!/usr/bin/env python3

from flask import Flask,request,render_template,Response,redirect,send_from_directory
from flask_cache import Cache
from os import makedirs
from os.path import dirname,basename,join,exists
from requests import get
from yaml import load
from starch import Archive,Package
from tempfile import TemporaryDirectory
from contextlib import closing
from starch.utils import valid_key,valid_path
from hashlib import sha256,md5
from tempfile import NamedTemporaryFile

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
cache = Cache(app, config={ 'CACHE_TYPE': 'simple' })
with open('config.yml') as f:
    config = load(f)
archive = Archive(config['archive']['root'])

@app.route('/<key>/')
def package(key):
    return return_file(key, '_package.json')


@app.route('/<key>/<path:path>', methods=[ 'GET' ])
def package_file(key, path):
    return return_file(key, path)


@app.route('/<key>/<path:path>', methods=[ 'PUT' ])
def put_file(key, path):
    if 'expected_hash' not in request.args:
        return 'parameter expected_hash missing', 400

    try:
        path = valid_path(path)
        key = valid_key(key)
        expected_hash = request.args['expected_hash']
        replace = 'replace' in request.args and request.args['replace'] == 'True'

        if path in request.files:
            if expected_hash.startswith('md5'):
                h = md5()
            elif expected_hash.startswith('sha256'):
                h = sha256()
            else:
                return 'unsupported hash function \'%s\'' % expected_hash.split(':')[0], 400

            with NamedTemporaryFile() as tempfile:
                with open(tempfile.name, 'wb') as o:
                    b = None
                    while b != b'':
                        b = request.files[path].read(100*1024)
                        o.write(b)
                        h.update(b)

                h2 = expected_hash.split(':')[0] + ':' + h.digest().hex()
                if h2 != expected_hash:
                    return 'expected hash %s, got %s' % (expected_hash, h2), 400

                p = archive.get(key, mode='a')
                p.add(tempfile.name, path, replace=replace)

            return 'done', 204
        else:
            return 'path (%s) not found in request' % path, 400
    except Exception as e:
        return str(e), 400


@app.route('/<key>/<path:path>', methods=[ 'DELETE' ])
def delete_file(key, path):
    try:
        package = archive.get(key, mode='a')

        if path not in package:
            return 'Not found', 404

        package.remove(path)
        
        return '', 204
    except Exception as e:
        return str(e), 400


@app.route('/ingest', methods=[ 'POST' ])
def ingest():
    with TemporaryDirectory() as tempdir:
        # @todo: this probably breaks with very large packages
        for path in request.files:
            temppath=join(tempdir, valid_path(path))

            if not exists(dirname(temppath)):
                makedirs(dirname(temppath))

            with open(temppath, mode='wb') as o:
                b=None
                while b != b'':
                    b=request.files[path].read(100*1024)
                    o.write(b)

        key=requests.args['key'] if 'key' in request.args else None

        return redirect('/%s/' % archive.ingest(Package(tempdir), key=key), code=201)


@app.route('/new', methods=[ 'POST' ])
def new():
    return redirect('/%s/' % archive.new()[0], code=201)

@app.route('/packages')
def packages():
    return '\n'.join([ x for x in archive ])


@app.route('/<key>/finalize', methods=[ 'POST' ])
def finalize(key):
    p = archive.get(key)

    if archive.get(key).status() == 'finalized':
        return 'packet is finalized, use patch(...)', 400
    else:
        archive.get(key, mode='a').finalize()

        return 'finalized', 200


def return_file(key, path, as_attachment=False):
    url = archive.get_location(key, path)

    if url:
        if url.startswith('file://'):
            return send_from_directory(
                        dirname(url[7:]),
                        basename(url),
                        as_attachment=as_attachment,
                        attachment_filename=path)
        elif loc.startswith('http://') or loc.startswith('https://'):
            return Response(iter_response(loc, path))
        else:
            return 'Unknown URL-scheme', 500
    else:
        return 'Not found', 404


def iter_response(url, path):
    with closing(get(url, stream=True)) as r:
        for chunk in r.iter_content(100*1024):
            yield chunk


if __name__ == "__main__":
    app.debug=True
    app.run(host='0.0.0.0')


