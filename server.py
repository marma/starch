#!/usr/bin/env python3

from flask import Flask,session,request,render_template,Response,redirect,send_from_directory,make_response
from flask_caching import Cache
from flask_basicauth import BasicAuth
from yaml import load as yload,FullLoader
from starch import Archive,Package,Index
from starch.exceptions import RangeNotSupported
from contextlib import closing
from json import loads,dumps,load
from hashlib import md5,sha256
from starch.elastic import ElasticIndex
from starch.utils import decode_range,valid_path,max_iter,guess_content,flatten_structure
from os.path import join
from tempfile import NamedTemporaryFile,TemporaryFile,TemporaryDirectory
from time import time
from traceback import print_exc
from re import match
from requests import get
from math import log2
from tarfile import TarFile,TarInfo,open as taropen
from os import SEEK_END
from os.path import basename,dirname,exists
from starch.iterio import IterIO
import datetime
from sys import stdout
from io import UnsupportedOperation

USE_NGINX_X_ACCEL = False

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
#app.use_x_sendfile = True
app.config.update(yload(open(join(app.root_path, 'config.yml')).read(), Loader=FullLoader))
app.jinja_env.line_statement_prefix = '#'
cache = Cache(app, config={ 'CACHE_TYPE': 'simple' })

if 'auth' in app.config:
    basic_auth = BasicAuth(app)
    app.config['BASIC_AUTH_USERNAME'] = app.config['auth']['user']
    app.config['BASIC_AUTH_PASSWORD'] = app.config['auth']['pass']
    app.config['BASIC_AUTH_FORCE'] = True

archive = Archive(**app.config['archive'])
index = Index(**app.config['archive']['index']) if 'index' in app.config['archive'] else None

@app.route('/')
def site_index():
    q = request.args.get('q', None) or {}
    tpe = request.cookies.get('type', 'Package')
    result = (index or archive).search(q, max=200, level=tpe, include=True)
    #descriptions = [ (x, index.get(x) if index else archive.get(x).description()) for x in packages[3] ]
    descriptions = [ x for x in result.keys ]
    counts = (index or archive).count(
                    q,
                    { 
                        'type': { 'files': 'mime_type' },
                        'tag': 'tags',
                        'created': 'meta.year.keyword',
                        'size': 'sum(size)'
                    },
                    level=tpe)

    #print(descriptions)

    counts['size']['value'] = int(counts['size']['value'])

    r = Response(
            render_template('conspiracy.html',
                            start=result.start,
                            max=result.m,
                            n_packages=result.n,
                            #archive=archive,
                            descriptions=descriptions,
                            counts=counts,
                            query=q))

    return r


@app.route('/_set')
def set():
    r = Response(headers={ 'Location': request.headers.get("Referer") })
    
    for p in request.args:
        r.set_cookie(p, request.args[p])

    return r, 302


@app.route('/<key>')
def view_thing(key):
    _check_base(request)
 
    p = archive.get(key)

    print(p)

    return render_template('thing.html', structure=dumps(loads(archive.read(key, 'structure.json'))))

    ret = (index or archive).get(key)

    if ret:
        return Response(dumps(ret, indent=4), mimetype='application/json')
    else:
        return 'Not found', 404


@app.route('/<key>/')
@app.route('/<key>/_package.json')
def package(key):
    _check_base(request)

    #return package_file(key, '_package.json')

    #ret = (index or archive).get(key)
    ret = archive.get(key)

    if ret:
        return Response(dumps(ret.description(), indent=4), mimetype='application/json')
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
    _check_base(request)

    t0=time()
    p = archive.get(key)
    t1=time()

    if p:
        desc = p.description() if not isinstance(p, dict) else p
        desc['files'] = { x['path']:x for x in desc['files'] }
        mode = request.cookies.get('view', 'list')

        if 'structure.json' not in p:
            mode = 'list'

        t2=time()
        structure = loads(p.read('structure.json')) if 'structure.json' in p and mode == 'structure' else None
        entities = loads(p.read('entities.json')) if 'entities.json' in p else None
        structure = loads(p.read('structure.json')) if mode == 'structure' and 'structure.json' in p else []
        t3=time()

        r = Response(
                render_template(
                    'package.html',
                    package=desc,
                    mode=mode,
                    structure=flatten_structure(structure),
                    entities=entities),
                mimetype='text/html')
        t4=time()
        print('time: ', t1-t0, t2-t1, t3-t2, t4-t3, t4-t0)

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
    _check_base(request)

    p = archive.get(key)
    if p and path in p:
        callback = app.config.get('image_server', {}).get('callback_root', request.url_root)
        url = f'{callback}{key}/{path}'
        uri = f'{p.description()["@id"]}{path}'

        if app.config.get('image_server', {}).get('send_location', False):
            loc = p.location(path)

            if loc.startswith('file:'):
                prefix = app.config.get('image_server', {}).get('prefix', None)
                base = app.config.get('image_server', {}).get('archive_root', None)

                if prefix:
                    url = loc[7:].replace(base, f'{prefix}:')

        if uri == '':
            uri = f'{request.url_root}{key}/{path}'

        image_url = app.config.get('image_server').get('root') + 'info'

        print(image_url, uri, url, flush=True)

        with closing(get(image_url, params={ 'uri': uri, 'url': url })) as r:
            i = loads(r.text)
            i['id'] = f'/{key}/{path}'
            i['levels'] = [ 2**x for x in range(0, int(log2(min(i['width']-1, i['height']-1)) + 1 - int(log2(512)))) ]

            return i

    return None


# @todo avoid clash with files actually named info.json
@app.route('/<key>/<path:path>/info.json')
def iiif_info(key, path):
    _check_base(request)

    if archive.exists(key, path):
        i = _info(key, path)
        r = Response(render_template('info.json', **i), mimetype='application/json')
        r.headers['Access-Control-Allow-Origin'] = '*'
    
        return r

    return 'Not found', 404


@app.route('/<key>/<path:path>/<region>/<size>/<rot>/<quality>.<fmt>')
def iiif(key, path, region, size, rot, quality, fmt):
    _check_base(request)
    _assert_iiif()

    if archive.exists(key, path):
        iconf = app.config.get('image_server', {})
        loc = archive.location(key, path)

        if loc.startswith('file:'):
            if iconf.get('send_location', False):
                # send image using an internal prefix that is known by the image server
                prefix = app.config['image_server']['prefix']
                base = app.config['image_server']['archive_root']
                url = loc[7:].replace(base, f'{prefix}:')
            elif iconf.get('callback_root', False):
                # send image location to image server using callback since the internal
                # name within Docker may not be the same as the external one
                url = f'{iconf["callback_root"]}{key}/{path}'
            else:
                # simply use the request url
                url = f'{request.url_root}{key}/{path}'
        else:
            url = loc

        uri = app.config['archive']['base'] + key + '/' + path
        image_url = iconf['root'] + 'image'

        params = { 'uri': uri,
                   'url': url,
                   'region': region,
                   'size': size,
                   'rotation': rot,
                   'quality': quality,
                   'format': fmt, }

        print(image_url, uri, url, flush=True)

        r = get(image_url, params=params, stream=True)

        if r.status_code != 200:
            return f'Image server returned {r.status_code}', 500

        return Response(
                r.iter_content(100*1024),
                mimetype=r.headers.get('Content-Type', 'application/unknown'))

    return 'Not found', 404


@app.route('/<key>/_label', methods = [ 'POST' ])
def set_label(key):
    _check_base(request)

    try:
        p = archive.get(key, mode='a')

        if p:
            #print(request.form.get('label'))
            p.label = request.form.get('label')

            return f'Changed label to "{p.label}"'

        return 'Not found', 404
    except Exception as e:
        return str(e), 500


@app.route('/<key>/<path:path>/_manifest')
def iiif_manifest(key, path):
    _assert_iiif()

    return 'IIIF manifest'


@app.route('/<key>/_serialize')
def download(key):
    _check_base(request)
    p = archive.get(key)

    if not p:
        return 'Not found', 404

    i = archive.serialize(
            key,
            resolve=request.args.get('resolve', 'true').lower() == 'true',
            iter_content=True,
            buffer_size=100*1024)

    return Response(i, headers={ 'Content-Disposition': f'attachment; filename={key}.tar' }, mimetype='application/x-tar')


@app.route('/<key>/<path:path>', methods=[ 'GET' ])
def package_file(key, path):
    _check_base(request)

    # Fast x-send-file if possible
    loc = archive.location(key, path)

    if loc and loc.startswith('file://'):
        if USE_NGINX_X_ACCEL:
            r = make_response()
            r.headers['X-Accel-Redirect'] = loc[7:]
            r.headers['Content-Type'] = guess_content(path)
            r.headers['filename'] = path
            return r
        else:
            # quick fix for html
            if path.endswith('aspx') or path.endswith('html'):
                return Request(open(loc).read(), headers={ 'Content-Type': 'text/plain' })

            return send_from_directory(dirname(loc[7:]), basename(loc[7:]))


    # Do things manually

    p = archive.get(key)

    if p and path in p:
        size = int(p[path]['size'])
        #headers = { 'Content-Disposition': f'inline; filename={basename(path)}' }
        headers = {}

        # fast hack for pretty JSON
        if (p[path].get('mime_type', 'unknown') == 'application/json' or path.endswith('.json')) and 'pretty' in request.args:
            return Response(dumps(loads(p.get_raw(path).read().decode('utf-8')), indent=2), mimetype='application/json'), 200

        # quick fix for html
        if p[path].get('mime_type', 'unknown') == 'text/html':
            return Response(p.get_raw(path).read(), headers={ 'Content-Type': 'text/plain' })

        if 'checksum' in p[path]:
            headers.update({ 'ETag': p[path]['checksum'].split(':')[1] })

        if 'size' in p[path]:
            headers.update({ 'Content-Length': p[path]['size'] })

        range = decode_range(request.headers.get('Range', default='bytes=0-'))

        try:
            i = p.get_iter(path, range=range)
            headers.update({ 'Accept-Ranges': 'bytes' })

            if range != ( 0, None ):
                headers.update({ 'Content-Range': 'bytes %d-%s/%d' % (range[0], str(range[1]) if range[1] != None else size-1, size) })
                headers.update({ 'Content-Length': range[1]-range[0] + 1 if range[1] != None else size-range[0] })
        except UnsupportedOperation:
            i = p.get_iter(path)
            range = (0, None)
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
    _check_base(request)

    #print(request.args)

    type = str(request.args.get('type', 'Resource'))

    if type != 'Reference' and 'expected_hash' not in request.args:
        #print(type, type == 'Reference', flush=True)
        return 'parameter expected_hash missing', 400

    try:
        p = archive.get(key, mode='a')

        if p:
            path = valid_path(path)
            url = request.args.get('url', None)
            expected_hash = request.args.get('expected_hash', None)
            replace = request.args.get('replace', 'False') == 'True'

            args = { k:v for k,v in request.args.items() if k not in [ 'type', 'path', 'replace', 'url', 'expected_hash' ] }

            if url and type == 'Reference':
                p.add(path=path, url=url, replace=replace, type=type, **args)

                return 'done', 204
            else:
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
                        p.add(tempfile.name, path=path, replace=replace, type=type, **args)

                    return 'done', 204
                else:
                    return 'path (%s) not found in request' % path, 400
        else:
            return 'package not found', 400
    except Exception as e:
        print_exc()
        print(flush=True)

        return str(e), 500


@app.route('/<key>/<path:path>', methods=[ 'DELETE' ])
def delete_file(key, path):
    _check_base(request)
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


@app.route('/ingest', defaults={'key': None })
@app.route('/ingest/<key>', methods=[ 'POST' ])
def ingest(key):
    _check_base(request)

    if app.config['archive'].get('mode', 'read-only') != 'read-write':
        return 'Archive is read-only', 500

    with TemporaryDirectory() as tempdir:
        # TODO: this probably breaks with very large packages
        # TODO: implement serialize(...) so this can be done over TAR
        # TODO: validate checksum
        # TODO: cleanup on failure
        for path in request.files:
            temppath=join(tempdir, valid_path(path))

            if not exists(dirname(temppath)):
                makedirs(dirname(temppath))

            with open(temppath, mode='wb') as o:
                b=None
                while b != b'':
                    b=request.files[path].read(100*1024)
                    o.write(b)

            
        key = archive.ingest(Package(tempdir), key=key)
        package = archive.get(key)

        return redirect('/%s/' % key, code=201)


@app.route('/_deserialize', methods=[ 'POST' ])
def deserialize():
    _check_base(request)

    key = archive.deserialize(request.stream, key=request.args.get('key', None))

    return redirect(f'/{key}/', code=201)


@app.route('/new', methods=[ 'POST' ])
def new():
    _check_base(request)
    #print(request.args)
    key, package = archive.new(**{k:loads(v) if v[0] in [ '{', '[' ] else v for k,v in request.args.items() })

    return redirect('/%s/' % key, code=201)


@app.route('/packages')
def packages():
    return Response(newliner((index or self)), mimetype='text/plain')


@app.route('/<key>/finalize', methods=[ 'POST' ])
def finalize(key):
    _check_base(request)

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
    return app.config['archive']['base'] if 'base' in app.config['archive'] else request.url_root


@app.route('/_search')
@app.route('/search')
def search():
    if request.args.get('q', '') == '':
        return 'non-existant or empty q parameter', 500

    tpe = request.args.get('@type', None)
    include = 'include' in request.args and request.args['include'] not in [ 'False', 'false' ]

    r = (index or archive).search(
            loads(request.args['q']),
            int(request.args.get('from', '0')),
            int(request.args['max']) if 'max' in request.args else None,
            request.args.get('sort', None),
            level=tpe,
            include=include)

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
    p=archive.get(key)

    if not p:
        index.delete(key)

        return 'Not found', 404    

    #print(index, p, flush=True)

    if index != None and p:
        try:
            index.update(key, p)

            return 'OK', 200
        except Exception as e:
            raise e
            #return str(e), 500

    #if index:
    #    t0 = time()
    #    ps = [ (k,archive.get(k)) for k in key.split(';') if k ]
    #    t1 = time()
    #    b = index.bulk_update(ps, sync=False)
    #    t2 = time()

        #print(f'getting {len(ps)} packages took {t1-t0} seconds, index returned after {t2-t1}', flush=True)

    #    return dumps(b)

    return 'no index', 500



@app.route('/deindex/<key>')
def deindex(key):
    if index:
        b = index.delete(key)

        return "ok"

    return 'no index', 500


@app.route('/favicon.ico')
def favicon():
    return 'Not found', 404

def _check_base(request):
    if 'base' not in app.config['archive']:
        app.config['archive']['base'] = request.url_root
        archive.base = request.url_root


def _assert_iiif():
    if app.config.get('image_server', {}).get('url', '') != '':
        raise Exception('No image server')

#@app.route('/static/<path:path>')
#def static(path):
#    return send_from_directory('static', path)

def iter_search(start, returned, count, gen):
    yield '%d %d %d\n' % (start, returned, count)

    for id in gen:
        if isinstance(id, tuple):    
            yield str(id[0]) + ',' + dumps(id[1]) + '\n'
        else:
            yield id + '\n'


def newliner(g):
    for x in g:
        yield x + '\n'


if __name__ == "__main__":
    app.debug=True
    app.run(host='0.0.0.0', threaded=True)

