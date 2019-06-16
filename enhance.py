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
import starch
from starch.utils import pdf_to_textarray

starch.VERIFY_CA=False

if __name__ == "__main__":
    if len(argv) == 1:
        print(f'usage: {basename(argv[0])} <URL / location>')
        exit(1)
    loc = argv[1]

    if loc.startswith('http'):
        r = get(loc, verify=False)

        if r.status_code == 401:
            auth = (input('Username: '), getpass())
        else:
            auth = None

        a = Archive(loc, auth=auth)
    else:
        a = Archive(loc)

    for package_id in a:
        structure = []
        content = []
        partn = 1
        print(package_id)

        package_id = package_id.strip()

        get_package_start = timer()
        package = a.get(package_id, mode='a')
        get_package_end = timer()

        if 'content.json' in package:
            print('content.json already in package')
            continue

        get_page = 0.0
        for path in package:
            info = package[path]

            if info.get('mime_type', '') == 'application/pdf':
                get_bytes_start = timer()
                b = BytesIO(package.get_raw(path).read())
                get_bytes_end = timer()

                part_id = f'{info["@id"]}#{partn}'
                part = { '@id': part_id, '@type': 'Part', 'extracted_from': path, 'has_part': [] }

                extract_content_start = timer()
                text_array = pdf_to_textarray(b)
                extract_content_end = timer()

                for i,page_data in enumerate(pdf_to_textarray(b)):
                    page_id = f'{part_id}-{i+1}'
                    page = { '@id': page_id, '@type': 'Page', 'content': [ page_data] }

                    content += [ deepcopy(page) ]
                    del(page['content'])
                    part['has_part'] += [ page ]

            structure += [ part ]

        partn += 1

        add_data_start = timer()
        if content:
            package.add(path='content.json', replace=True, data=content, type='Content')

        if structure:
            package.add(path='structure.json', replace=True, data=structure, type='Structure')
        add_data_end = timer()

        print(f'{package_id} total:{add_data_end - get_package_start} get_package:{get_package_end-get_package_start} get_bytes:{get_bytes_end-get_bytes_start} extract_content:{extract_content_end-extract_content_start} add_data:{add_data_end-add_data_start}')

