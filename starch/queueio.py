#!/usr/bin/env python3

from sys import stderr
from io import RawIOBase,UnsupportedOperation,BufferedWriter,TextIOWrapper,BlockingIOError,DEFAULT_BUFFER_SIZE
from queue import Queue

def open(q, mode='wb', producer=None, buffering=-1, encoding=None):
    if mode != 'wb':
        raise Exception('only write-only binary streams supported')

    if encoding != None:
        raise ValueError('binary mode doesn\'t take an encoding argument')

    if buffering == 1:
        raise ValueError('line buffering not supported in binary mode')


    if not isinstance(buffering, int):
        raise TypeError('an integer is required (got type %s)' % type(buffering).__name__)

    raw = QueueIO(q)
    buf = raw

    if buffering != 0:
        buf = BufferedWriter(raw, buffer_size=DEFAULT_BUFFER_SIZE if buffering < 2 else buffering)

    return buf


class QueueIO(RawIOBase):
    def __init__(self, q):
        self.queue = q

    def write(self, b):
        if self.closed:
            raise ValueError('I/O operation on closed stream')

        #print(len(b), file=stderr)

        self.queue.put(bytes(b))

        return len(b)


    def flush(self):
        ...


    def writable(self):
        return True


    def readable(self):
        return False


    def close(self):
        if not self.closed:
            self.queue.put(None)

        super().close()


    def __iter__(self):
        t=self.queue.get()

        while t != None:
            yield t
            t=self.queue.get()

