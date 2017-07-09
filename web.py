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

        return redirect('/%s/' % archive.ingest(Package(tempdir), key=key), code=302)


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


