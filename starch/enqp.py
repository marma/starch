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
# contributor:{ role:aut and agent:{ name:pelle and lastName:Olsson } }
#

from sys import argv,stdin,stderr
from lark import Lark
from json import dumps
from copy import deepcopy
from re import match

debug = True

def parse(query, default='_all'):
    parser = Lark(
            """
            query:          or_query
            single:         asterisk | expr | "(" query ")" | nested_query
            or_query:       and_query (or and_query)*
            and_query:      single ([and | "," | and_not] single)*
            not_query:      single and_not single
            nested_query:   "{" query "}"
            and:            "and"i
            or:             "or"i
            and_not:        ["and"i] "not"i
            expr:           (string | fielded_expr)
            fielded_expr:   field ":" single
            field:          CNAME | "\\"" CNAME "\\""
            string:         CNAME | ESCAPED_STRING
            asterisk:       "*"
            CNAME:          /[a-z\u00e5\u00e4\u00f6A-Z\u00c5\u00c4\u00d60-9_\\.-]+/
            %import common.ESCAPED_STRING
            %import common.WS
            %ignore WS
            """,
            start='query',
            parser='lalr')

    x = parser.parse(query)

    if debug:
        print(x.pretty(), file=stderr)

    return { 'query': _handle(x, default=default) }


def _handle(node, field='', default='_all'):
    if node.data in [ 'query', 'single' ] or node.data in [ 'or_query', 'and_query' ] and len(node.children) == 1:
        return _handle(node.children[0], field, default=default)
    elif node.data == 'or_query':
        return  {
                    'bool': {
                        #'min_should_match': 1,
                        'should': [
                            _handle(x, field, default=default) for x in node.children if x.data != 'or'
                        ]
                    }
                }
    elif node.data == 'and_query':
        mode='and'
        a=[]
        n=[]
        for x in node.children:
            if x.data in [ 'and', 'and_not' ]:
                mode = x.data
            elif mode == 'and':
                a += [ x ]
            elif mode == 'and_not':
                n += [ x ]
 

        ret = {
                'bool': {
                    'must': [
                        _handle(x, field, default=default) for x in a
                    ]
                }
            }

        if len(n) != 0:
            ret['bool'].update(
                    {
                        'must_not': [
                            _handle(x, field, default=default) for x in n
                        ]
                    })

        return ret
    elif node.data == 'nested_query':
        return {
                'nested': {
                    'path': field,
                    'query': _handle(node.children[0], field, default=default)
                    }
                } if field != '' else _handle(node.children[0], default=default)
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

        #return { 'match': { field if field != '' else default: { 'query': s, 'operator': 'and' } } }
        return { 'term': { field if field != '' else default: s } } 


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
    print(parse(argv[1]))

