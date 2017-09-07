from requests import get,post
from urllib.parse import urljoin
from contextlib import closing
from json import dumps,loads
import starch

MAX_ID=2**38

class HttpArchive(starch.Archive):
    def __init__(self, root=None, base=None, auth=None):
        url=root
        self.url = url + ('/' if url[-1] != '/' else '')
        self.auth = auth
        self.base = base or url
        self.server_base = get(urljoin(self.url, 'base')).text

    def new(self, **kwargs):
        r = post(urljoin(self.url,'new'), params=kwargs, auth=self.auth, allow_redirects=False)
        
        if r.status_code != 201:
            raise Exception('expected HTTP status 201, but got %d' % r.status_code)

        url = r.headers['Location']

        return (self.get_key(url),
                starch.Package(
                    url,
                    mode='a',
                    auth=self.auth,
                    server_base=url.replace(self.url, self.base)))


    def ingest(self, package, key=None):
        files = { path:package.get_raw(path) for path in package }
        r = post(self.url + 'ingest', files=files, auth=self.auth)

        if r.status_code != 201:
            raise Exception('expected HTTP status 201, but got %d with content %s' % (r.status_code, r.text))

        url = r.headers['Location']

        return self.get_key(url)


    def get(self, key, mode='r'):
        try:
            return starch.Package(
                    self.url + key + '/',
                    mode=mode,
                    base=urljoin(self.base, key + '/'),
                    auth=self.auth,
                    server_base=urljoin(self.server_base, key + '/'))
        except:
            return None


    def search(self, query, frm=None, max=None):
        params = { 'q': dumps(query) }

        if frm: params.update({ 'from': frm })
        if max: params.update({ 'max': max })

        with closing(get(urljoin(self.url, 'search'),
                         params=params,
                         auth=self.auth,
                         stream=True)) as r:
            if r.status_code == 200:
                for key in r.raw:
                    yield key[:-1].decode('utf-8')
            else:
                raise Exception('Expected status 200, got %d' % r.status_code)


    def get_location(self, key, path):
        return self.url + key + '/' + path


    def __iter__(self):
        with closing(get(self.url + 'packages', auth=self.auth, stream=True)) as r:
            if r.status_code == 200:
                for key in r.raw:
                    yield key[:-1].decode('utf-8')
            elif r.status_code != 404:
                raise Exception('server returned status %d' % r.status)


    def get_key(self, url):
        if url.startswith(self.url):
            return url[len(self.url):].split('/')[0]

        raise Exception('url (%s) does start with %s' % (url, self.url))


    def __contains__(self, key):
        with closing(get(self.url + key + '/')) as r:
            return r.status_code == 200


