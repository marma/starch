#!/usr/bin/env python3

# Elasticsearch Nested Query Parser
#
# Examples:
#
# matches documents when name and lastName match any nested objects separately
#   nested.name:pelle AND nested.lastName:Olsson
#
# matches document only when name and lastName match the same nested object
#   nested:{ name: Pelle, lastName: Olsson }
#
# match multiple levels of nested objects:
#   contributor:{ role: aut, agent: { name: Pelle, lastName: Olsson } }
#
# Alternative:
#
# nested:{ role:aut and agent:{ name:pelle and lastName:Olsson } }
#

from sys import argv,stdin,stderr
from lark import Lark
from json import dumps
from copy import deepcopy
from re import match

debug = False

def parse(query, default='_all'):
    parser = Lark('query:          query_part | boolean_query\n' +
            'query_part:     asterisk | expr | dictionary | "(" query ")" | nested_query\n' +
            'boolean_query:  query_part operator query_part (operator query_part)*\n' +
            'nested_query:   "{" query "}"\n' +
            'dictionary:     "{" [key_val] ("," key_val)* "}"\n' +
            'key_val:        field ":" (string | dictionary)\n' +
            'operator:       and | or\n' + # | and_not\n' +
            'and:            "and"i\n' +
            'or:             "or"i\n' +
            #'and_not:        "and not"i\n' +
            'expr:           string | fielded_expr\n' +
            'fielded_expr:   field ":" (string | dictionary | nested_query)\n' +
            'field:          CNAME | "\\"" CNAME "\\""\n' +
            'string:         CNAME | ESCAPED_STRING\n' +
            'asterisk:       "*"\n' +
            'CNAME:          /[a-z\u00e5\u00e4\u00f6A-Z\u00c5\u00c4\u00d60-9_\\.-]+/\n' +
            '%import common.ESCAPED_STRING\n' +
            '%import common.WS\n' +
            '%ignore WS',
            start='query')

    x = parser.parse(query)

    if debug:
        print(x.pretty(), file=stderr)

    return { 'query': _handle(x, default=default) }


def _handle(node, field='', default='_all'):
    if node.data in [ 'query', 'query_part']:
        return _handle(node.children[0], field, default=default)
    elif node.data == 'nested_query':
        return {
                'nested': {
                    'path': field,
                    'query': _handle(node.children[0], field, default=default)
                    }
                } if field != '' else _handle(node.children[0], default=default)
    elif node.data == 'dictionary':
        if len(node.children) == 0:
            if field != '':
                return  {
                        'nested': {
                            'path': field,
                            'query': { 'match_all': {} }
                            }
                        }
            else:
                return { 'match_all': {} }
        else:
            if field != '':
                return {
                        'nested': {
                            'path': field,
                            'query': {
                                'bool': {
                                    'must': [ _handle(kv, field) for kv in node.children ]
                                    }
                                } if len(node.children) > 1 else _handle(node.children[0], field, default=default)
                            }
                        }
            else:
                return  {
                        'bool': {
                            'must': [ _handle(kv, field, default=default) for kv in node.children ]
                            }
                        } if len(node.children) > 1 else _handle(node.children[0], field, default=default)
    elif node.data == 'key_val':
        return _handle(node.children[1], '.'.join([field, node.children[0].children[0].value]) if field != '' else node.children[0].children[0].value, default=default)
    elif node.data == 'boolean_query':
        # 1. split on "or" operator
        should,c = [], []

        for t in node.children:
            if t.data == 'operator' and t.children[0].data == 'or':
                should.append(c)
                c = []
            else:
                c += [ t ]

        should.append(c)

        if len(should) == 1:
            return  {
                    'bool': {
                        'must': [
                            _handle(x, field, default=default) for x in should[0] if x.data != 'operator'
                            ]
                        }
                    }
        else:
            return  {
                    'bool': {
                        'min_should_match': 1,
                        'should': [
                            _handle(l[0], field, default=default) if len(l) == 1 else
                            {
                                'bool': {
                                    'must': [
                                        _handle(x, field, default=default) for x in l if x.data != 'operator'
                                        ]
                                    }
                                } for l in should 
                            ]
                        }
                    }
    elif node.data == 'asterisk':
        return { 'match_all': {} }
    elif node.data == 'expr':
        return _handle(node.children[0], field, default=default)
    elif node.data == 'fielded_expr':
        f = node.children[0].children[0].value

        return _handle(node.children[1], field + '.' + f if field != '' else f, default=default)
    elif node.data == 'string':
        s = node.children[0].value

        if s[0] == '"':
            s = s[1:-1]

        return { 'match': { field if field != '' else default: { 'query': s, 'operator': 'and' } } }


def create_aggregations(q):
    return { 'aggregations': { k:_handle_agg(k, q[k]) for k in q } }


def _handle_agg(name, value, prefix=None):
    if isinstance(value, dict):
        if len(value) != 1:
            raise Exception('dict must have exactly one key')

        key,dvalue = next(iter(value.items()))
        path = prefix + '.' + key if prefix else key

        return { 'nested': { 'path': path }, 'aggregations': { name: _handle_agg(name, dvalue, path) } }
    #if '.' in value:
    #    s = value.split('.')
    #    path = prefix + '.' + s[0] if prefix else s[0]
    #
    #    return { 'nested': { 'path': path }, 'aggregations': { name: _handle_agg(name, '.'.join(s[1:]), path) } }
    elif match(r'sum\(([a-z0-9]*)\)', value):
        value = match(r'sum\(([a-z]*)\)', value).group(1)
        return { 'sum' : { 'field' : value } }
    else:
        return { 'terms': { 'field': prefix + '.' + value if prefix else value, 'size': 10 } }


def _flatten_aggs(name, r):
    while name in r:
        r = r[name]

    return r

def flatten_aggs(r):
    r2=None
    if 'aggregations' in r:
        for name,agg in r['aggregations'].items():
            if name in agg:
                if r2 == None:
                    r2 = deepcopy(r)

                r2['aggregations'][name] = _flatten_aggs(name, r2['aggregations'][name])

    return r2 or r


if __name__ == "__main__":
    parse(sys.argv[1])



