from starch import HttpPackage
from requests import get,post
from contextlib import closing

MAX_ID=2**38

class HttpArchive:
    def __init__(self, url, auth=None):
        self.url = url + ('/' if url[-1] != '/' else '')
        self.auth = auth


    def new(self, **kwargs):
        r = post(self.url + 'new', params=kwargs, auth=self.auth, allow_redirects=False)
        
        if r.status_code != 201:
            raise Exception('expected HTTP status 201, but got %d' % r.status_code)

        url = r.headers['Location']

        return (self.get_key(url), HttpPackage(url, mode='a', auth=self.auth))


    def ingest(self, package, key=None):
        files = { path:package.get_raw(path) for path in package }
        r = post(self.url + 'ingest', files=files, auth=self.auth)

        if r.status_code != 201:
            raise Exception('expected HTTP status 201, but got %d with content %s' % (r.status_code, r.text))

        url = r.headers['Location']

        return self.get_key(url)


    def get(self, key, mode='r'):
        return HttpPackage(self.url + key + '/', mode=mode, auth=self.auth)


    def get_location(self, key, path):
        return self.url + key + '/' + path


    def __iter__(self):
        with closing(get(self.url + 'packages', auth=self.auth, stream=True)) as r:
            for key in r.raw:
                yield key[:-1].decode('utf-8')


    def get_key(self, url):
        if url.startswith(self.url):
            return url[len(self.url):].split('/')[0]

        raise Exception('url (%s) does start with %s' % (url, self.url))

