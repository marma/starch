import starch
from sys import stderr
from threading import RLock,Lock
from contextlib import contextmanager

class LockManager():
    def __new__(cls, type='memory', **kwargs):
        if type == 'memory':
            return super().__new__(starch.MemoryLockManager)
        elif type == 'null':
            return super().__new__(starch.NullLockManager)
        elif type == 'redlock':
            return super().__new__(starch.RedLockManager)

        raise Exception('Unknown lock type')


class NullLockManager(LockManager):
    def __init__(self, type='null', debug=False):
        self.debug = debug


    @contextmanager
    def get(self, key):
        if self.debug:
            print('LOCK %s' % key, file=stderr)

        yield

        if self.debug:
            print('UNLOCK %s' % key, file=stderr)


class MemoryLockManager(LockManager):
    def __init__(self, type='memory', debug=False):
        self._global_lock = RLock()
        self._locks = {}


    def get(self, key):
        with self._global_lock:
            # TODO use a contextmanager, or similiar, to remove
            # released locks from self._locks since this becomes
            # increasingly inefficient for a large number of
            # open locks
            for k in [ x for x in self._locks if not self._locks[x].locked() ]:
                del self._locks[k]

            if key not in self._locks:
                self._locks[key] = Lock()

            return self._locks[key]


#    def _release(self, key):
#        with self.global_lock:
#            if key in self.locks:
#                self.locks[key].release()
#
#
#class LockContextManager():
#    def __init__(self, manager, key, rlock):
#        self.manager = manager
#        self.key = key
#        self.rlock = rlock
#
#    def __enter__(self):
#        self.rclock.acquire()
#
#
#    def __
#

