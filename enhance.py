#!/usr/bin/env python3

from timeit import default_timer as timer
from PyPDF2 import PdfFileReader
from getpass import getpass
from requests import get
from starch import Archive
from sys import exit,argv,stdin,stdout,stderr
from os.path import basename
from io import BytesIO
from json import load,loads,dump,dumps
from copy import deepcopy
from traceback import print_exc
import starch
from starch.utils import pdf_to_textarray
from collections import Counter

starch.VERIFY_CA=False

def enhance(package, base):
    t,s,c = Counter(), None, None
    if 'aip.mets.metadata' in package and any(( path.endswith('_alto.xml') for path in package )):
        # Alto
        t,s,c = enhance_alto(package, base)
    elif any(( package[path].get('mime_type', '') == 'application/pdf' for path in package )):
        # PDF
        t,s,c = enhance_pdf(package, base)

    if content:
        add_data_start = timer()
        package.add(path='content.json', replace=True, data=dumps(content, indent=2), type='Content', mime_type='application/json')
        package.add(path='structure.json', replace=True, data=dumps(structure, indent=2), type='Structure', mime_type='application/json')
        t.update({ 'add_data': timer() - add_data_start })
    else:
        return { 'status': 'no content' }, None, None        

    return t, structure, content

                
def enhance_pdf(package, base):
    print(f'Enhance PDF {base}', flush=True)

    structure = []
    content = []
    timings = Counter()
    part = 1

    for path in package:
        info = package[path]

        if package[path].get('mime_type', 'unknown') == 'application/pdf':
            try:
                get_bytes_start = timer()
                b = BytesIO(package.get_raw(path).read())
                get_bytes_end = timer()

                part_id = f'{info["@id"]}#{partn}'
                part = { '@id': part_id, '@type': 'Part', 'extracted_from': path, 'has_part': [] }

                extract_content_start = timer()
                text_array = pdf_to_textarray(b)
                extract_content_end = timer()

                for i,page_data in enumerate(text_array):
                    page_id = f'{part_id}-{i+1}'
                    page = { '@id': page_id, '@type': 'Page', 'content': [ page_data] }

                    content += [ deepcopy(page) ]
                    del(page['content'])
                    part['has_part'] += [ page ]

                structure += [ part ]
                added = True
            except KeyboardInterrupt:
                exit(1)
            except:
                print_exc()
                print('', flush=True, file=stderr)
                print('', flush=True, file=stdout)
                continue
            finally:
                partn += 1

            enhance_pdf(package, path, part)
            part += 1
        

def alto_content(package, base):
    print(f'Enhance Alto {base}', flush=True)

    structure = []
    content = []
    part = 1

    mets = etree.fromstring(package.get_raw('aip.mets.metadata').read())

    

    alto = etree.fromstring(package.get_raw(path).read())

    for page in alto.findall('.//{http://www.loc.gov/standards/alto/ns-v2#}Page'):
        page_id = page.attrib["ID"]

        for area in alto.findall('.//{http://www.loc.gov/standards/alto/ns-v2#}ComposedBlock'):
            area_id = area.attrib["ID"]

            for block in area.findall('*'):
                b = { '@id': f'{base}#{page_id}-{area_id}-{block.attrib["ID"]}', '@type': '', 'partOf': f'{base}#{page_id}-{area_id}' }
                content = []

                if block.tag == '{http://www.loc.gov/standards/alto/ns-v2#}TextBlock':
                    b['@type'] = 'Text'

                for line in block.findall('{http://www.loc.gov/standards/alto/ns-v2#}TextLine'):
                    for x in line.findall('*'):
                        if x.tag == '{http://www.loc.gov/standards/alto/ns-v2#}String':
                            if 'SUBS_CONTENT' in x.attrib:
                                if x.attrib.get('SUBS_TYPE', None) == 'HypPart1':
                                    content += [ x.attrib['SUBS_CONTENT'] ]
                            else:
                                content += [ x.attrib['CONTENT'] ]
                        elif x.tag == '{http://www.loc.gov/standards/alto/ns-v2#}SP':
                            content += [ ' ' ]

                b['content'] = ''.join(content)

                ret += [ b ]

    return ret

def stripgen(i):
    for l in i:
        yield l.strip()


if __name__ == "__main__":
    if len(argv) == 1:
        print(f'usage: {basename(argv[0])} [options] <URL / location>')
        exit(1)

    loc = argv[1]

#    if loc.startswith('http'):
#        r = get(loc, verify=False)
#
#        if r.status_code == 401:
#            auth = (input('Username: '), getpass())
#        else:
#            auth = None
#
#        a = Archive(loc, auth=auth)
#    else:
#        a = Archive(loc)

    a = Archive('https://betalab.kb.se/', auth=('demo', 't89ughurguyqw476t8ayguhjtr'))

    #for package_id in [ 'sou-1971-58' ]:
    for package_id in stripgen(stdin):
        structure = []
        content = []
        print(package_id, flush=True)
        partn = 1

        get_package_start = timer()
        package = a.get(package_id, mode='a')
        get_package_end = timer()

        if 'content.json' in package:
            print('content.json already in package', flush=True)
            continue

        ret = enhance(package, a.base + package_id)

        print(ret)
