#!/usr/bin/env python3

from flask import Flask,request,render_template,Response,redirect,send_from_directory
from flask_caching import Cache
from flask_basicauth import BasicAuth
from yaml import load
from starch import Archive,Package,Index
from starch.exceptions import RangeNotSupported
from contextlib import closing
from json import loads,dumps
from hashlib import md5,sha256
from starch.elastic import ElasticIndex
from starch.utils import decode_range,valid_path,max_iter
from os.path import join
from tempfile import NamedTemporaryFile,TemporaryFile,TemporaryDirectory
from time import time
from traceback import print_exc
from re import match
from requests import get
from math import log2
from tarfile import TarFile,TarInfo,open as taropen
from os import SEEK_END
from starch.iterio import IterIO
import datetime

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config.update(load(open(join(app.root_path, 'config.yml')).read()))
app.jinja_env.line_statement_prefix = '#'
cache = Cache(app, config={ 'CACHE_TYPE': 'simple' })

if 'auth' in app.config:
    basic_auth = BasicAuth(app)
    app.config['BASIC_AUTH_USERNAME'] = app.config['auth']['user']
    app.config['BASIC_AUTH_PASSWORD'] = app.config['auth']['pass']
    app.config['BASIC_AUTH_FORCE'] = True

archive = Archive(**app.config['archive'])
index = Index(**app.config['index']) if 'index' in app.config else None

@app.route('/')
def site_index():
    q = request.args['q'] if 'q' in request.args else {}
    packages = (index or archive).search(q, max=50)
    descriptions = [ (x, index.get(x) if index else archive.get(x).description()) for x in packages[3] ]
    counts = (index or archive).count(q, { 'type': { 'files': 'mime_type' }, 'tag': 'tags', 'size': 'sum(size)' } )
    counts['size']['value'] = int(counts['size']['value'])

    return render_template('index.html',
                           start=packages[0],
                           max=packages[1],
                           n_packages=packages[2],
                           archive=archive,
                           descriptions=descriptions,
                           counts=counts,
                           query=q)


@app.route('/<key>/')
@app.route('/<key>/_package.json')
def package(key):
    ret = (index or archive).get(key)

    if ret:
        return Response(dumps(ret, indent=4), mimetype='application/json')
    else:
        return 'Not found', 404


@app.route('/<key>/_tag', methods=[ 'POST' ])
def tag(key):
    p = archive.get(key, mode='a')

    if p:
        if 'tag' in request.form or 'untag' in request.form:
            for tag in request.form.getlist('tag'):
                p.tag(tag)

            for tag in request.form.getlist('untag'):
                p.untag(tag)

            return 'Done', 200
        else:
            return "parameter 'tag' or 'untag' missing", 400
    else:
        return 'Not found', 404


@app.route('/<key>/_view')
def view_package(key):
    #p = (index or archive).get(key)
    p = (index.get(key) if index else None) or archive.get(key)

    if p:
        p = p.description() if not isinstance(p, dict) else p
        p['files'] = { x['path']:x for x in p['files'] }
        r = Response(render_template('package.html', package=p, mode=request.args.get('mode', request.cookies.get('mode', 'list'))), mimetype='text/html')

        if 'mode' in request.args:
            r.set_cookie('mode', request.args['mode'])

        return r
    else:
        return 'Not found', 404


@app.route('/<key>/_log')
def log(key):
    p = archive.get(key)
   
    if p: 
        return Response(p.log(), mimetype='text/plain')

    return 'Not found', 404


@app.route('/<key>/<path:path>/_view')
def view(key, path):
    _assert_iiif()

    i = _info(key, path)

    if i:
        return render_template('view.html', info=i)
    else:
        return 'Not found', 404


def _info(key, path):
    _assert_iiif()

    p = archive.get(key)
    if p and path in p:
        callback = app.config.get('image_server', {}).get('callback_root', request.url_root)
        url = f'{callback}{key}/{path}'
        uri = f'{p.description()["@id"]}{path}'

        if uri == '':
            uri = f'{request.url_root}{key}/{path}'

        image_url = app.config.get('image_server').get('root') + 'info'

        with closing(get(image_url, params={ 'uri': uri, 'url': url })) as r:
            i = loads(r.text)
            i['id'] = f'/{key}/{path}'
            i['levels'] = [ 2**x for x in range(0, int(log2(min(i['width']-1, i['height']-1)) + 1 - int(log2(512)))) ]

            return i

    return None


# @todo avoid clash with files actually named info.json
@app.route('/<key>/<path:path>/info.json')
def iiif_info(key, path):
    _assert_iiif()

    i = _info(key, path)
    r = Response(render_template('info.json', **i), mimetype='application/json')
    r.headers['Access-Control-Allow-Origin'] = '*'

    return r


@app.route('/<key>/<path:path>/<region>/<size>/<rot>/<quality>.<fmt>')
def iiif(key, path, region, size, rot, quality, fmt):
    _assert_iiif()

    p = archive.get(key)
    if p:
        # pdf page selection?
        m = match('^(.*)(?::)(\\d+)$', path)

        if path in p or (m and m.group(1) in p and p[m.group(1)]['mime_type'] == 'application/pdf'):
            callback = app.config.get('image_server', {}).get('callback_root', request.url_root)
            url = f'{callback}{key}/{path}'
            uri = (p.description()['@id'] or request.url_root + key + '/') + path
            image_url = app.config.get('image_server').get('root') + 'image'
            params = { 'uri': uri,
                       'url': url,
                       'region': region,
                       'size': size,
                       'rotation': rot,
                       'quality': quality,
                       'format': fmt }

            r = get(image_url, params=params, stream=True)

            return Response(
                    r.iter_content(100*1024),
                    mimetype=r.headers.get('Content-Type', 'application/unknown'))

    return 'Not found', 404


@app.route('/<key>/_label', methods = [ 'POST' ])
def set_label(key):
    try:
        p = archive.get(key, mode='a')

        if p:
            print(request.form.get('label'))
            p.label = request.form.get('label')

            return f'Changed label to "{p.label}"'

        return 'Not found', 404
    except Exception as e:
        return str(e), 500


@app.route('/<key>/<path:path>/_manifest')
def iiif_manifest(key, path):
    _assert_iiif()

    return 'IIIF manifest'


@app.route('/<key>/_download')
def download(key):
    fmt = request.args.get('format', 'application/gzip')
    p = archive.get(key)

    if not p:
        return 'Not found', 404

    i = download_package_iterator(key, p, fmt)
    size,filename = next(i)

    return Response(i, headers={ 'Content-Disposition': f'attachment; filename={filename}' }, mimetype=fmt)


def download_package_iterator(key, p, fmt):
    mimes = { 
                'application/gzip': ('tar.gz', 'w:gz'),
                'application/x-tar': ('tar', 'w'),
                'application/bzip2': ('tar.bz2', 'w:bz2')
            }

    if fmt not in mimes:
        raise Exception('Unsupported format')

    with TemporaryFile() as f:
        t = taropen(fileobj=f, mode=mimes[fmt][1])

        for path in p:
            ti = TarInfo(f'{key}/{path}')
            ti.size = int(p[path]['size'])
            ti.mtime = int(datetime.datetime.fromisoformat(p.description()['created'][:-1]).timestamp())
            t.addfile(ti, IterIO(p.get_iter(path)))
 
        t.close()
        f.seek(0, SEEK_END)

        yield f.tell(), f'{key}.{mimes[fmt][0]}'

        f.seek(0)
        b = f.read(1024*1024)
        while b != b'':
            yield b
            b = f.read(1024*1024)


@app.route('/<key>/<path:path>', methods=[ 'GET' ])
def package_file(key, path):
    print('package_file')

    p = archive.get(key)

    if p and path in p:
        size = int(p[path]['size'])
        headers = { 'ETag': p[path]['checksum'].split(':')[1],
                    'Content-Length': p[path]['size'] }

        range = decode_range(request.headers.get('Range', default='bytes=0-'))

        # TODO optimization using get_location and send_from_directory

        try:
            i = p.get_iter(path, range=range)
            headers.update({ 'Accept-Ranges': 'bytes' })

            if range != ( 0, None ):
                headers.update({ 'Content-Range': 'bytes %d-%s/%d' % (range[0], str(range[1]) if range[1] != None else size-1, size) })
                headers.update({ 'Content-Length': range[1]-range[0] + 1 if range[1] != None else size-range[0] })
        except RangeNotSupported:
            i = p.get_iter(path)
        except:
            raise

        max_bytes = request.args.get('max_bytes', None)
        if max_bytes:
            headers['Content-Length'] = min(int(max_bytes), int(headers['Content-Length']))

        return Response(
                i if not max_bytes else max_iter(i, int(max_bytes)),
                headers=headers,
                mimetype=p[path].get('mime_type', 'application/unknown'),
                status=200 if range == (0, None) else 206)

    return 'Not found', 404


@app.route('/<key>/<path:path>', methods=[ 'PUT' ])
def put_file(key, path):
    if 'expected_hash' not in request.args:
        return 'parameter expected_hash missing', 400

    try:
        p = archive.get(key, mode='a')

        if p:
            path = valid_path(path)
            expected_hash = request.args['expected_hash']
            replace = request.args.get('replace', 'False') == 'True'

            if path in request.files:
                if expected_hash.startswith('MD5:'):
                    h = md5()
                elif expected_hash.startswith('SHA256:'):
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
        else:
            return 'package not found', 400
    except Exception as e:
        print_exc()
        return str(e), 500


@app.route('/<key>/<path:path>', methods=[ 'DELETE' ])
def delete_file(key, path):
    package = archive.get(key, mode='a')

    if package and path in package:
        package.remove(path)

        return 'deleted', 204
    
    return 'Not found', 404


@app.route('/<key>/', methods=[ 'DELETE' ])
def delete_package(key):
    try:
        p = archive.get(key, mode='a')

        if p:
            archive.delete(key, force=True)        

            return 'deleted', 204

        return 'Not found', 404
    except Exception as e:
        return e.message, 500


@app.route('/ingest', methods=[ 'POST' ])
def ingest():
    with TemporaryDirectory() as tempdir:
        # TODO: this probably breaks with very large packages
        for path in request.files:
            temppath=join(tempdir, valid_path(path))

            if not exists(dirname(temppath)):
                makedirs(dirname(temppath))

            with open(temppath, mode='wb') as o:
                b=None
                while b != b'':
                    b=request.files[path].read(100*1024)
                    o.write(b)

        key = archive.ingest(Package(tempdir), key=request.args.get('key', None))
        package = archive.get(key)

        return redirect('/%s/' % key, code=201)


@app.route('/new', methods=[ 'POST' ])
def new():
    key, package = archive.new(**{k:v for k,v in request.args.items() })

    return redirect('/%s/' % key, code=201)


@app.route('/packages')
def packages():
    return Response(newliner((index or self)), mimetype='text/plain')


@app.route('/<key>/finalize', methods=[ 'POST' ])
def finalize(key):
    p = archive.get(key, mode='a')

    if p:
        if p.status() == 'finalized':
            return 'packet is finalized, use patches', 400
        else:
            p.finalize()

            return 'finalized', 200
    else:
        return 'Not found', 404


@app.route('/base')
def base():
    return app.config['archive'].get('base', request.url_root)


@app.route('/search')
def search():
    if 'q' not in request.args:
        return 'no q parameter', 500

    r = (index or archive).search(
            loads(request.args['q']),
            int(request.args.get('from', '0')),
            int(request.args['max']) if 'max' in request.args else None,
            request.args.get('sort', None))

    return Response(
            iter_search(r.start, r.n, r.m, r.keys),
            mimetype='text/plain')


@app.route('/count')
def count():
    return Response(
                dumps(
                    (index or archive).count(
                        loads(request.args['q']),
                        loads(request.args['c']))) + '\n',
                mimetype='application/json')


@app.route('/reindex/<key>')
def reindex(key):
    if index:
        t0 = time()
        ps = [ (k,archive.get(k)) for k in key.split(';') if k ]
        t1 = time()
        b = index.bulk_update(ps, sync=False)
        t2 = time()

        print(f'getting {len(ps)} packages took {t1-t0} seconds, index returned after {t2-t1}', flush=True)

        return '\n'.join(b) + '\n'

    return 'no index', 500



@app.route('/deindex/<key>')
def deindex(key):
    if index:
        b = index.delete(key)

        return "ok"

    return 'no index', 500


def _assert_iiif():
    if app.config.get('image_server', {}).get('url', '') != '':
        raise Exception('No image server')

#@app.route('/static/<path:path>')
#def static(path):
#    return send_from_directory('static', path)

def iter_search(start, returned, count, gen):
    yield '%d %d %d\n' % (start, returned, count)

    for id in gen:
        yield id + '\n'


def newliner(g):
    for x in g:
        yield x + '\n'


if __name__ == "__main__":
    app.debug=True
    app.run(host='0.0.0.0', threaded=True)

