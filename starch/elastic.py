import starch
from json import dumps,loads,load
from elasticsearch_dsl import Document, InnerDoc, Date, Integer, Search, Keyword, Long, Mapping, Nested, Text
from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.exceptions import NotFoundError,RequestError
from copy import deepcopy
from starch.enqp import parse,flatten_aggs,create_aggregations
from starch.utils import rebase
from elasticsearch_dsl import connections

class File(InnerDoc):
    id = Keyword(multi=False)
    type = Keyword()
    checksum = Keyword()
    path = Keyword()
    urn = Keyword()
    size = Long()
    mime_type = Keyword()    


class Package(Document):
    id = Keyword(multi=False, store=True, required=True)
    type = Keyword()
    tags = Keyword()
    version = Keyword()
    urn = Keyword()
    described_by = Keyword()
    label = Text(fields={ 'raw': Keyword() })
    patches = Keyword()
    created = Date()
    patch = Keyword(multi=True)
    status = Keyword()
    see_also = Keyword(multi=True)
    package_version = Keyword()
    content = Text(multi=True)
    files = Nested(File)
    size = Long()


class ElasticIndex(starch.Index):
    def __init__(self, type='elastic', url=None, base=None, index_name=None, server_base=None, index_content=False, default=None):
        if not (url and index_name):
            raise Exception('both url and index_name-parameters required')

        self.url = url
        self.base = base
        self.server_base = server_base
        self.index_name = index_name
        self.elastic = Elasticsearch(url)
        self.indices = IndicesClient(self.elastic)
        self.index_content = index_content
        self.default = default or ''

        if not self.indices.exists(self.index_name):
            try:
                Package.init(index=self.index_name, using=self.elastic)
                #self.indices.create(self.index_name)
                #self._install_mapping()
                self.index_existed = False
            except RequestError as e:
                if e.error == 'resource_already_exists_exception':
                    self.indices = IndicesClient(self.elastic)
                    self.index_existed = True
                else:
                    raise e
        else:
            self.index_existed = True


    def get(self, id):
        try:
            source = self.elastic.get(self.index_name, id)['_source']
            desc = { "@id": source['id'], "@type": source['type'] }
            del(source['id'])
            del(source['type'])
            desc.update(source)
            
            for f in desc['files']:
                f['@id'] = f['id']
                del(f['id'])
                f['@type'] = f['type']
                del(f['type'])

            if 'content' in desc:
                del(desc['content'])

            return rebase(
                    desc,
                    self.base,
                    self.server_base,
                    in_place=True)
        except NotFoundError:
            return None
        except:
            raise


    def search(self, q, start=0, max=None, sort=None):
        if isinstance(q, dict):
            q = dumps(q)

        query = parse(q, default=self.default)

        #print(query, flush=True)

        res = self.elastic.search(index=self.index_name, from_=0, size=0, body=query, track_total_hits=True)
        #print(res)
        count = int(res['hits']['total']['value'])
        key_iter = self._search_iterator(query, start, max, count, sort)

        return starch.Result(
                    start,
                    min(count-start, max) if max else count-start,
                    count,
                    key_iter,
                    iter([]))


    def _search_iterator(self, q, start, max, count, sort):
        max = max or count

        s = Search(using=self.elastic, index=self.index_name)
        s.extra(track_total_hits=True)
        s.update_from_dict(q)
        s.source(False)

        for i,hit in enumerate(s.scan()):
            # @TODO: find a way to paginate using Elastic since this is costly
            if i >= start:
                if i - start < max:
                    yield hit.meta.id
                else:
                    return


    def count(self, q, cats):
        if isinstance(q, dict):
            q = dumps(q)

        q = parse(q, default=self.default)
        q.update(create_aggregations(cats))

        res = self.elastic.search(
            index=self.index_name,
            #doc_type='package',
            size=0,
            body=q)

        ret = {}
        for k,v in flatten_aggs(res)['aggregations'].items():
            ret[k] = { x['key']:x['doc_count'] for x in v['buckets'] } if 'buckets' in v else v

        return ret
            

    def bulk_update(self, p, sync=True):
        bulk = [ ]

        #print(p)

        for key,package in p:
            if package:
                #bulk += [ dumps({ 'index': { '_index': self.index_name, '_type': 'package', '_id': key } }) ]
                bulk += [ dumps({ 'index': { '_index': self.index_name, '_id': key } }) ]
                bulk += [ dumps(self._format_package(package)) ]
            else:
                #bulk += [ dumps({ 'delete': { '_index': self.index_name, '_type': 'package', '_id': key } }) ]
                bulk += [ dumps({ 'delete': { '_index': self.index_name, '_id': key } }) ]

        #print(p)
        #print('\n'.join(bulk), flush=True)

        r = self.elastic.bulk(
                body='\n'.join(bulk),
                refresh=sync)

        #r2 = [ (x[next(iter(x))]['_id'], next(iter(x)), x[next(iter(x))]['result']) for x in r['items'] ]

        #return [ ' '.join(x) for x in r2 ]

        return r


    def update(self, key, p):
        self.elastic.index(
            index=self.index_name,
            #doc_type='package',
            id=key,
            body=self._format_package(p))


    def delete(self, key):
        self.elastic.delete(
                index=self.index_name,
                #doc_type='package',
                id=key,
                refresh=True)


    def iter_packages(self, start=0, max=None):
        for key in self.search({}, start=start, max=max).keys:
            yield key


    def __iter__(self):
        return self.iter_packages()


    def destroy(self, force=False):
        if self.index_existed and not force:
            raise Exception('Elastic index existed before creation of this Index instance and force parameter not set')

        self.indices.delete(self.index_name)


    def _format_package(self, p):
        desc = { "@id": "", "@type": "" }
        desc.update(p.description())

        # @id -> id and @type -> type since Elastic DSL does not allow '@' in field names
        desc['id'] = desc['@id']
        del(desc['@id'])
        desc['type'] = desc['@type']
        del(desc['@type'])
       
        for f in desc['files']:
            f['id'] = f['@id']
            del(f['@id'])
            f['type'] = f['@type']
            del(f['@type'])

        for path in p:
            if p[path]['@type'] == 'Content' and self.index_content:
                if 'content' not in desc:
                    desc['content'] = []

                desc['content'] += [ x['content'] for x in load(p.get_raw(path)) ]
            elif p[path]['@type'] == 'Meta':
                if 'meta' not in desc:
                    desc['meta'] = {}

                desc['meta'].update(load(p.get_raw(path)))
            
        return desc
        

    def _install_mapping(self):
        m = Mapping('package')
        m.meta('_all', enabled=False)

        m.field('@id', 'keyword', multi=False, store=True, required=True)
        m.field('@type', 'keyword')
        m.field('tags', 'keyword')
        m.field('version', 'keyword')
        m.field('urn', 'keyword')
        m.field('described_by', 'keyword')
        m.field('label', 'text', fields={ 'raw': Keyword() })
        m.field('patches', 'keyword')
        m.field('created', 'date')
        m.field('patch', 'keyword', multi=True)
        m.field('status', 'keyword')
        m.field('see_also', 'keyword')
        m.field('package_version', 'keyword')
        m.field('content', 'text')
        m.field('size', 'integer')

        #c = Nested(
        #        properties={
        #            '@id': Keyword(multi=False),
        #            '@type': Keyword(multi=False),
        #            'part_of': Keyword(),
        #            'content': Text()
        #        })
        #
        #m.field('content', c)

        f = Nested(
                properties={
                    '@id': Keyword(multi=False),
                    '@type': Keyword(),
                    'checksum': Keyword(),
                    'path': Keyword(),
                    'urn': Keyword(),
                    'size': Long(),
                    'mime_type': Keyword()
                })

        m.field('files', f)

        m.save(self.index_name, using=self.elastic)

