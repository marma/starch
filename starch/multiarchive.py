import starch

class MultiArchive(starch.Archive):
    def __init__(self, root=None, extras=[], base=None):
        archives=root
        self.archives = [ archives ] if not isinstance(archives, list) else archives
        self.extras = [ extras ] if not isinstance(extras, list) else extras
        self.base=base


    def get(self, key, mode='r'):
        if mode != 'r':
            raise Exception('only \'r\' mode supported for MultiArchive')

        for archive in self.archives:
            package = archive.get(key)
            if package:
            #if key in archive:
            #    package = archive.get(key)

                patches = [ extra.get(pkey) for extra in self.extras for pkey in extra.search({ 'patches': package.description()['urn'] }) ]

                return starch.MultiPackage(
                            package,
                            with_patches=sorted(patches, key=lambda x: x.description()['created']),
                            base=self.base + key + '/' if self.base else None)

        return None


    def search(self, query, frm=None, max=None):
        # @TODO implement from and max parameters
        for archive in self.archives:
            for key in archive.search(query):
                yield key


    def __iter__(self):
        for archive in self.archives:
            for key in archive:
                yield key

    def __contains__(self, key):
        for archive in self.archives:
            if key in archive:
                return True

        return False

