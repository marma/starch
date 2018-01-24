import starch
from json import dumps,loads
from elasticsearch_dsl import Keyword, Mapping, Nested, Text
from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.exceptions import NotFoundError
from copy import deepcopy
from enqp import parse,flatten_aggs,create_aggregations
from starch.utils import rebase

class ElasticIndex(starch.Index):
    def __init__(self, type='elastic', url=None, base=None, index_name=None, server_base=None):
        if not (url and index_name):
            raise Exception('both url and index_name-parameters required')

        self.url = url
        self.base = base
        self.server_base = server_base
        self.index_name = index_name
        self.elastic = Elasticsearch(url)
        self.indices = IndicesClient(self.elastic)

        if not self.indices.exists(self.index_name):
            self.indices.create(self.index_name)
            self._install_mapping()
            self.index_existed = False
        else:
            self.index_existed = True


    def get(self, id):
        try:
            return rebase(
                    self.elastic.get(self.index_name, id)['_source'],
                    self.base,
                    self.server_base,
                    in_place=True)
        except NotFoundError:
            return None
        except:
            raise


    def search(self, q, start=0, max=None, sort=None):
        query = parse(dumps(q))

        #print(query)

        res = self.elastic.search(index=self.index_name, doc_type='package', from_=0, size=0, body=query)
        count = int(res['hits']['total'])

        # TODO: use scan for large datasets
        return (start,
                min(count-start, max) if max else count-start,
                count,
                self._search_iterator(
                    query,
                    start,
                    max,
                    count,
                    sort))
                    #[ x['_source'] for x in res['hits']['hits'] ])


    def _search_iterator(self, q, start, max, count, sort):
        max = max or count

        # TODO: use scan for large datasets
        for n in range(0, min(max-1, (count-start-1))//100 + 1):
            res = self.elastic.search(
                    index=self.index_name,
                    doc_type='package',
                    from_=start+n*100,
                    size=min(100, count-start-100*n),
                    body=q)

            for id in [ x['_id'] for x in res['hits']['hits'] ]:
                yield id


    def count(self, q, cats):
        q = parse(dumps(q))
        q.update(create_aggregations(cats))

        #print(q)

        res = self.elastic.search(
            index=self.index_name,
            doc_type='package',
            size=0,
            body=q)

        #print(dumps(res, indent=4))

        ret = {}
        for k,v in flatten_aggs(res)['aggregations'].items():
            ret[k] = { x['key']:x['doc_count'] for x in v['buckets'] }

        return ret
            

    def update(self, key, package):
        print('index')
        self.elastic.index(
                index=self.index_name,
                doc_type='package',
                id=key,
                body=package.description(),
                refresh=True)


    def iter_packages(self, start=0, max=None):
        s,r,c,g = self.search({}, start, max)

        # TODO: use scan
        for i in self._search_iterator({}, start, max, c, None):
            yield i

        return ret


    def destroy(self, force=False):
        if self.index_existed and not force:
            raise Exception('Elastic index existed before creation of this Index instance and force parameter not set')

        self.indices.delete(self.index_name)


    def _install_mapping(self):
        m = Mapping('package')
        m.meta('_all', enabled=False)

        m.field('@id', 'keyword', multi=False, required=True)
        m.field('@type', 'keyword')
        m.field('urn', 'keyword')
        m.field('described_by', 'keyword')
        m.field('label', 'text', fields={ 'raw': Keyword() })
        m.field('patches', 'keyword')
        m.field('created', 'date')
        m.field('has_patches', 'keyword', multi=True)
        m.field('status', 'keyword')
        m.field('package_version', 'keyword')
        m.field('metadata', 'object')

        f = Nested()
        f.field('@id', 'keyword', multi=False)
        f.field('@type', 'keyword')
        f.field('checksum', 'keyword')
        f.field('path', 'keyword')
        f.field('urn', 'keyword')
        f.field('size', 'long')
        f.field('mime_type', 'keyword')

        m.field('files', f)

        m.save(self.index_name, using=self.elastic)

