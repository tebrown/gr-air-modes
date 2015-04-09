#
# Copyright 2010 Nick Foster
# 
# This file is part of gr-air-modes
# 
# gr-air-modes is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# gr-air-modes is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with gr-air-modes; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 


import time, os, sys, socket
import air_modes
from air_modes.exceptions import *
import threading
import traceback
from string import split, join
import datetime
import struct
from binascii import unhexlify

def float_to_bytes(f):
    s = struct.pack('>f', f)
    return long_to_bytes(struct.unpack('>l', s)[0])

def long_to_bytes (val, endianness='big'):
    """
    Use :ref:`string formatting` and :func:`~binascii.unhexlify` to
    convert ``val``, a :func:`long`, to a byte :func:`str`.

    :param long val: The value to pack

    :param str endianness: The endianness of the result. ``'big'`` for
      big-endian, ``'little'`` for little-endian.

    If you want byte- and word-ordering to differ, you're on your own.

    Using :ref:`string formatting` lets us use Python's C innards.
    """

    # one (1) hex digit per four (4) bits
    width = val.bit_length()

    # unhexlify wants an even multiple of eight (8) bits, but we don't
    # want more digits than we need (hence the ternary-ish 'or')
    width += 8 - ((width % 8) or 8)

    # format width specifier: four (4) bits per hex digit
    fmt = '%%0%dx' % (width // 4)

    # prepend zero (0) to the width, to zero-pad the output
    s = unhexlify(fmt % val)

    if endianness == 'little':
        # see http://stackoverflow.com/a/931095/309233
        s = s[::-1]

    return s

class dumb_task_runner(threading.Thread):
    def __init__(self, task, interval):
        threading.Thread.__init__(self)
        self._task = task
        self._interval = interval
        self.shutdown = threading.Event()
        self.finished = threading.Event()
        self.setDaemon(True)
        self.start()

    def run(self):
        while not self.shutdown.is_set():
            self._task()
            time.sleep(self._interval)
        self.finished.set()

    def close(self):
        self.shutdown.set()
        self.finished.wait(self._interval)

class output_beast:
  def __init__(self, cprdec, port, pub):
    self._s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("Listening for BEAST connections on %d" % port )
    self._s.bind(('', port))
    self._s.listen(1)
    self._s.setblocking(0) #nonblocking
    self._conns = [] #list of active connections

    self._cpr = cprdec

    #for i in (0,17):
    #pub.subscribe("modes_dl", self.output)
    pub.subscribe("raw", self.output)

    #spawn thread to add new connections as they come in
    self._runner = dumb_task_runner(self.add_pending_conns, 0.1)

  def __del__(self):
    self._s.close()

  def output(self, msg):
    for conn in self._conns[:]: #iterate over a copy of the list
      try:
        inBuf = long_to_bytes(msg.data)
        outBuf = b'\x1a'
        if len(inBuf) == 7:   # Short
            outBuf += b'2'
        elif len(inBuf) == 14:  # Long
            outBuf += b'3'
        elif len(inBuf) == 2:
            print("mode ac")
            outBuf += b'1'     # Mode AC
        else:
            #print(">> unknown len: %d" % len(inBuf))
            #print(inBuf)
            return

        ts = struct.pack('>d', msg.timestamp)
        #ts += '\x00\x00\x00\x00\x00\x00' #timestamp
        outBuf += ts[0:6]
        signalLevel = int(((60+msg.rssi)/60)*255)
        if (signalLevel) > 255: 
            signalLevel = 255
        if (signalLevel) < 0:
            signalLevel = 1
        outBuf += struct.pack('>B', signalLevel)
        outBuf += inBuf
        outBuf.replace('\x1a', '\x1a\x1a')

        conn.send(outBuf)
      except socket.error:
        self._conns.remove(conn)
        print "Connections: ", len(self._conns)

  def add_pending_conns(self):
    try:
      conn, addr = self._s.accept()
      self._conns.append(conn)
      print "Connections: ", len(self._conns)
    except socket.error:
      pass
