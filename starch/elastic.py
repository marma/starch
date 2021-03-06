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
        self.index_map = {}

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
            self.index_map[c['type']] = index
            
            if not self.indices.exists(index):
                try:
                    self.indices.create(index, ignore=400, body=mapping)
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


    def search(self, q, start=0, max=None, sort=None, level=None, include=False):
        if isinstance(q, dict):
            q = dumps(q)

        query = parse(q, default=self.default)

        index = self.index_map.get(level, self.index_name)
        res = self.elastic.search(index=index, from_=0, size=0, body=query, track_total_hits=True)
        count = int(res['hits']['total']['value'])
        key_iter = self._search_iterator(query, start, max, count, sort, level, include)

        return starch.Result(
                    start,
                    min(count-start, max) if max else count-start,
                    count,
                    key_iter,
                    iter([]))


    def _search_iterator(self, q, start, max, count, sort, level='Package', include=False):
        if max and start + max > 10_000:
            raise Exception('Pagination beyond 10000 hits not allowed, use empty max parameter to retrieve full set')

        index = self.index_map.get(level, self.index_name)

        #print(index, self.index_map, flush=True)
        s = Search(using=self.elastic, index=index)
        s.extra(track_total_hits=True)
        s.update_from_dict(q)
        s.source(include)

        m = max or count

        for hit in s[start:start+m] if start + m <= 10_000 else s.scan():
            yield hit.meta.id if not include else (hit.meta.id, self._hit_to_desc(hit))


    def count(self, q, cats, level=None):
        if isinstance(q, dict):
            q = dumps(q)

        q = parse(q, default=self.default)
        q.update(create_aggregations(cats))

        index = self.index_map.get(level, self.index_name) if level else self.index_name

        res = self.elastic.search(
            index=index,
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

        # TODO: deal with deletes
        if update_content and self.content and 'content.json' in p and 'structure.json' in p:
            # get structure and content files
            content = load(p.open('content.json'))
            structure = load(p.open('structure.json'))
            meta = load(p.open('meta.json')) if 'meta.json' in p else {}
    
            prefix = self.content.get('index_prefix', '')
            for ckey, config in self.content.get('parts', {}).items():
                #print(config, flush=True)
                index = prefix + config['index_name']
                f = flerge(p, level=config['type'], ignore=config.get('ignore', []))

                bulk = []
                for d in f:
                    #print(d)
                    k = d['@id']
                    #print(k)
                    k = k[k.rfind('/')+1:] if k[-1] != '/' else k[:-1][k[:-1].rfind('/')+1:]

                    if config['type'] != self.content.get('content_part_type', 'Text'):
                        l = d.get('content', [])
                        d['content'] = [ x['content'] for x in l if x.get('content', '') != '' ]

                    #self.elastic.index(
                    #    index=prefix + config['index_name'],
                    #    id=key,
                    #    body=self._reformat(d))

                    bulk += [ dumps({ 'index': { '_index': index, '_id': k } }) ]
                    bulk += [ dumps(self._reformat(d)) ]

                print(dumps(bulk, indent=2))

                if bulk:
                    self.elastic.bulk(
                        body='\n'.join(bulk),
                        refresh=sync)
        else:
            for ckey, config in self.content.get('parts', {}).items():
                if config.get('type', None)  == 'Package':
                    prefix = self.content.get('index_prefix', '')
                    index = prefix + config.get('index_name', '')

                    self.elastic.index(
                        index=index,
                        id=key,
                        body=self._format_package(p))
                    

    def delete(self, key):
        print('delete', key, flush=True)
        try:
            self.elastic.delete(
                    index=self.index_name,
                    id=key,
                    refresh=True)
        except:
            ...
            
        try:
            for ckey, config in self.content.get('parts', {}).items():
                print('delete', ckey, flush=True)
                if config.get('type', None)  == 'Package':
                    print('delete', ckey, 'Package', flush=True)
                    prefix = self.content.get('index_prefix', '')
                    index = prefix + config.get('index_name', '')
                    
                    print('delete', key, prefix, index, flush=True)

                    self.elastic.delete(
                            index=index,
                            id=key,
                            refresh=True)
        except Exception as e:
            ...


    def iter_packages(self, start=0, max=None):
        for key in self.search({}, start=start, max=max).keys:
            yield key


    def __iter__(self):
        return self.iter_packages()


    def destroy(self, force=False):
        if self.index_existed and not force:
            raise Exception('Elastic index existed before creation of this Index instance and force parameter not set')

        self.indices.delete(self.index_name)


    def _hit_to_desc(self, hit):
        d = hit.to_dict()
        ret = { '@id': d['id'], '@type': d['type'] }
        del(d['id'])
        del(d['type'])
        ret.update(d)
        
        return ret


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

