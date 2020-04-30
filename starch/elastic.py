import starch
from requests import put
from json import dumps,loads,load
from elasticsearch_dsl import Document, InnerDoc, Date, Integer, Search, Keyword, Long, Mapping, Nested, Text
from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.exceptions import NotFoundError,RequestError
from copy import deepcopy
from starch.enqp import parse,flatten_aggs,create_aggregations
from starch.utils import rebase
from elasticsearch_dsl import connections
from starch.mapping import mapping,content_mapping
from starch.utils import flerge

class ElasticIndex(starch.Index):
    def __init__(self, type='elastic', url=None, base=None, name=None, server_base=None, content=None, default=None):
        if not (url and name):
            raise Exception('both url and name-parameters required')

        self.url = url
        self.base = base
        self.server_base = server_base
        self.index_name = name
        self.elastic = Elasticsearch(url)
        self.indices = IndicesClient(self.elastic)
        self.index_content = content is not None
        self.content = content
        self.default = default or ''

        if not self.indices.exists(self.index_name):
            try:
                self.indices.create(self.index_name, ignore=400, body=mapping)
                self.index_existed = False
            except RequestError as e:
                if e.error == 'resource_already_exists_exception':
                    self.indices = IndicesClient(self.elastic)
                    self.index_existed = True
                else:
                    raise e
        else:
            self.index_existed = True

        for c in (content or {}).get('parts', {}).values():
            prefix = content.get('index_prefix', '')
            index = prefix + c['index_name']
            
            if not self.indices.exists(index):
                try:
                    self.indices.create(index, ignore=400, body=content_mapping)
                except RequestError as e:
                    if e.error == 'resource_already_exists_exception':
                        self.indices = IndicesClient(self.elastic)
                    else:
                        raise e


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


    def update(self, key, p, update_content=True, sync=True):
        self.elastic.index(
            index=self.index_name,
            #doc_type='package',
            id=key,
            body=self._format_package(p))

        if update_content and self.content and 'content.json' in p and 'structure.json' in p:
            # get structure and content files
            content = load(p.open('content.json'))
            structure = load(p.open('structure.json'))
            meta = load(p.open('meta.json')) if 'meta.json' in p else {}
    
            prefix = self.content.get('index_prefix', '')
            for key, config in self.content.get('parts', {}).items():
                print(config, flush=True)
                index = prefix + config['index_name']
                f = flerge(p, level=config['type'], ignore=config.get('ignore', []))

                bulk = []
                for d in f:
                    k = d['@id']
                    #print(dumps(d, indent=2))
    
                    if config['type'] != self.content.get('content_part_type', 'Text'):
                        l = d.get('content', [])
                        d['content'] = [ x['content'] for x in l if x.get('content', '') != '' ]

                    #self.elastic.index(
                    #    index=prefix + config['index_name'],
                    #    id=key,
                    #    body=self._reformat(d))

                    bulk += [ dumps({ 'index': { '_index': index, '_id': k } }) ]
                    bulk += [ dumps(self._reformat(d)) ]

                self.elastic.bulk(
                    body='\n'.join(bulk),
                    refresh=sync)

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
        desc.update(p.description(include=[ 'meta.json' ]))

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

#        for path in p:
#            if p[path]['@type'] == 'Content' and self.index_content:
#                if 'content' not in desc:
#                    desc['content'] = []
#
#                desc['content'] += [ x['content'] for x in load(p.get_raw(path)) ]
#            elif p[path]['@type'] == 'Meta':
#                if 'meta' not in desc:
#                    desc['meta'] = {}
#
#                desc['meta'].update(load(p.get_raw(path)))
            
        return desc

    def _reformat(self, d):
        ret = { 'id':d['@id'], 'type':d['@type'] }
        ret.update(d)
        ret['path'] = [ x['@id'] for x in ret['path'] ]
        del(ret['@id'])
        del(ret['@type'])

        return ret

