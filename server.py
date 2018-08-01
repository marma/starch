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
from tempfile import NamedTemporaryFile,TemporaryDirectory
from time import time
from traceback import print_exc

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config.update(load(open(join(app.root_path, 'config.yml')).read()))
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
    p = (index or archive).get(key)

    if p:
        cover = next(iter([ x['path'] for x in p['files'] if x.get('mime_type', '') in [ 'image/jpeg', 'image/gif', 'image/png' ] ]), None) 
        p['files'] = { x['path']:x for x in p['files'] }
        return render_template('package.html', package=p, cover=cover, mimetype='text/html')
    else:
        return 'Not found', 404


@app.route('/<key>/<path:path>', methods=[ 'GET' ])
def package_file(key, path):
    # must be some other way to get correct routing
    if key == 'reindex':
        return reindex(path if path[-1] != '/' else path[:-1])

    if path == '_view':
        return view_package(key)

    p = archive.get(key)

    if p and path == '_log':
        return Response(p.log(), mimetype='text/plain')

    # actually an IIIF request?
    m = match(r'^(.*)/(full|[0-9\,]+)/(full|max|[0-9\,]+)/([0-9\.]+)/default.(jpg|png)$', path)
    if 'iiif' in app.config and m:
        return iiif(key, *m.groups())

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

        key = archive.ingest(Package(tempdir), key=requests.args.get('key', None))
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
    return app.config['archive']['base']


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

        print('getting %d packages took %f seconds, index returned after %f' % (len(ps), t1-t0, t2-t1), flush=True)

        return '\n'.join(b) + '\n'

    return 'no index', 500


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

