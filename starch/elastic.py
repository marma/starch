from json import dumps,loads
from elasticsearch_dsl import Keyword, Mapping, Nested, Text
from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.exceptions import NotFoundError
from copy import deepcopy


class ElasticIndex():
    def __init__(self, base, index):
        self.base = base
        self.index = index
        self.elastic = Elasticsearch(base)
        self.indices = IndicesClient(self.elastic)

        if not self.indices.exists(self.index):
            self.indices.create(self.index)
            self._install_mapping()


    def get(self, id):
        try:
            ret = self.elastic.get(self.index, id)['_source']
        except NotFoundError:
            return None
        except:
            raise

        # inflate dict
        if ret:
            ret['files'] = { x['path']:x for x in ret['files'] }

        return ret


    def search(self, q, start=0, max=None, sort=None):
        query = self._create_query(q)

        #print(query)

        res = self.elastic.search(index=self.index, doc_type='package', from_=0, size=0, body=query)
        count = int(res['hits']['total'])

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
        for n in range(0, min(max-1, (count-start-1))//100 + 1):
            res = self.elastic.search(
                    index=self.index,
                    doc_type='package',
                    from_=start+n*100,
                    size=min(100, count-start-100*n),
                    body=q)

            for id in [ x['_id'] for x in res['hits']['hits'] ]:
                yield id


    def count(self, query, categories={}):
        q = self._create_query(query)
        q['aggregations'] = self._create_aggs(categories)

        res = self.elastic.search(
            index=self.index,
            doc_type='package',
            size=0,
            body=q)

        #print(dumps(res, indent=4))

        ret = {}
        for k,v in res['aggregations'].items():
            if k in categories:
                ret[k] = { x['key']:x['doc_count'] for x in v['buckets'] }
            else:
                # nested category
                # @TODO deal with more than one level of nesting
                for c in categories:
                    if c in v:
                        ret[c] = { x['key']:x['doc_count'] for x in v[c]['buckets'] }

        return ret
            

    def update(self, key, package):
        desc = deepcopy(package.description())

        # deflate dict
        desc['files'] = [ x for x in desc['files'].values() ]

        self.elastic.index(index=self.index, doc_type='package', id=key, body=desc, refresh=True)


    def iter_packages(self, start=0, max=None):
        s,r,c,g = self.search({}, start, max)

        for i in self._search_iterator({}, start, max, c, None):
            yield i


    def _create_query(self, query):
        return {
                'query': {
                    'bool': {
                        'must': [ { 'match': { x[0]: x[1] } } for x in query.items() ]
                    }
                }
            }


    def _create_aggs(self, cats={}):
        ret = {}
        for k,v in cats.items():
            if '.' in v:
                vs = v.split('.')

                ret[vs[0]] = {
                                'nested': {
                                    'path': vs[0]
                                },
                                'aggregations': {
                                    k: { 'terms': { 'field': v } }
                                }
                         }
            else:
                ret[k] = { 'terms': { 'field': v, 'size': 100 } }

        #print(ret)

        return ret
        #return { k:{ 'terms': { 'field': v, 'size': 100 } } for k,v in cats.items() }


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

        m.save(self.index, using=self.elastic)

