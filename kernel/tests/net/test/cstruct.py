# Copyright 2014 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A simple module for declaring C-like structures.

Example usage:

>>> # Declare a struct type by specifying name, field formats and field names.
... # Field formats are the same as those used in the struct module, except:
... # - S: Nested Struct.
... # - A: NULL-padded ASCII string. Like s, but printing ignores contiguous
... #      trailing NULL blocks at the end.
... import cstruct
>>> NLMsgHdr = cstruct.Struct("NLMsgHdr", "=LHHLL", "length type flags seq pid")
>>>
>>>
>>> # Create instances from a tuple of values, raw bytes, zero-initialized, or
>>> # using keywords.
... n1 = NLMsgHdr((44, 32, 0x2, 0, 491))
>>> print n1
NLMsgHdr(length=44, type=32, flags=2, seq=0, pid=491)
>>>
>>> n2 = NLMsgHdr("\x2c\x00\x00\x00\x21\x00\x02\x00"
...               "\x00\x00\x00\x00\xfe\x01\x00\x00" + "junk at end")
>>> print n2
NLMsgHdr(length=44, type=33, flags=2, seq=0, pid=510)
>>>
>>> n3 = netlink.NLMsgHdr() # Zero-initialized
>>> print n3
NLMsgHdr(length=0, type=0, flags=0, seq=0, pid=0)
>>>
>>> n4 = netlink.NLMsgHdr(length=44, type=33) # Other fields zero-initialized
>>> print n4
NLMsgHdr(length=44, type=33, flags=0, seq=0, pid=0)
>>>
>>> # Serialize to raw bytes.
... print n1.Pack().encode("hex")
2c0000002000020000000000eb010000
>>>
>>> # Parse the beginning of a byte stream as a struct, and return the struct
... # and the remainder of the stream for further reading.
... data = ("\x2c\x00\x00\x00\x21\x00\x02\x00"
...         "\x00\x00\x00\x00\xfe\x01\x00\x00"
...         "more data")
>>> cstruct.Read(data, NLMsgHdr)
(NLMsgHdr(length=44, type=33, flags=2, seq=0, pid=510), 'more data')
>>>
>>> # Structs can contain one or more nested structs. The nested struct types
... # are specified in a list as an optional last argument. Nested structs may
... # contain nested structs.
... S = cstruct.Struct("S", "=BI", "byte1 int2")
>>> N = cstruct.Struct("N", "!BSiS", "byte1 s2 int3 s2", [S, S])
>>> NN = cstruct.Struct("NN", "SHS", "s1 word2 n3", [S, N])
>>> nn = NN((S((1, 25000)), -29876, N((55, S((5, 6)), 1111, S((7, 8))))))
>>> nn.n3.s2.int2 = 5
>>>
"""

import ctypes
import string
import struct


def CalcSize(fmt):
  if "A" in fmt:
    fmt = fmt.replace("A", "s")
  return struct.calcsize(fmt)

def CalcNumElements(fmt):
  prevlen = len(fmt)
  fmt = fmt.replace("S", "")
  numstructs = prevlen - len(fmt)
  size = CalcSize(fmt)
  elements = struct.unpack(fmt, "\x00" * size)
  return len(elements) + numstructs


def Struct(name, fmt, fieldnames, substructs={}):
  """Function that returns struct classes."""

  class Meta(type):

    def __len__(cls):
      return cls._length

    def __init__(cls, unused_name, unused_bases, namespace):
      # Make the class object have the name that's passed in.
      type.__init__(cls, namespace["_name"], unused_bases, namespace)

  class CStruct(object):
    """Class representing a C-like structure."""

    __metaclass__ = Meta

    # Name of the struct.
    _name = name
    # List of field names.
    _fieldnames = fieldnames
    # Dict mapping field indices to nested struct classes.
    _nested = {}
    # List of string fields that are ASCII strings.
    _asciiz = set()

    _fieldnames = _fieldnames.split(" ")

    # Parse fmt into _format, converting any S format characters to "XXs",
    # where XX is the length of the struct type's packed representation.
    _format = ""
    laststructindex = 0
    for i in xrange(len(fmt)):
      if fmt[i] == "S":
        # Nested struct. Record the index in our struct it should go into.
        index = CalcNumElements(fmt[:i])
        _nested[index] = substructs[laststructindex]
        laststructindex += 1
        _format += "%ds" % len(_nested[index])
      elif fmt[i] == "A":
        # Null-terminated ASCII string.
        index = CalcNumElements(fmt[:i])
        _asciiz.add(index)
        _format += "s"
      else:
        # Standard struct format character.
        _format += fmt[i]

    _length = CalcSize(_format)

    offset_list = [0]
    last_offset = 0
    for i in xrange(len(_format)):
      offset = CalcSize(_format[:i])
      if offset > last_offset:
        last_offset = offset
        offset_list.append(offset)

    # A dictionary that maps field names to their offsets in the struct.
    _offsets = dict(zip(_fieldnames, offset_list))

    # Check that the number of field names matches the number of fields.
    numfields = len(struct.unpack(_format, "\x00" * _length))
    if len(_fieldnames) != numfields:
      raise ValueError("Invalid cstruct: \"%s\" has %d elements, \"%s\" has %d."
                       % (fmt, numfields, fieldnames, len(_fieldnames)))

    def _SetValues(self, values):
      # Replace self._values with the given list. We can't do direct assignment
      # because of the __setattr__ overload on this class.
      super(CStruct, self).__setattr__("_values", list(values))

    def _Parse(self, data):
      data = data[:self._length]
      values = list(struct.unpack(self._format, data))
      for index, value in enumerate(values):
        if isinstance(value, str) and index in self._nested:
          values[index] = self._nested[index](value)
      self._SetValues(values)

    def __init__(self, tuple_or_bytes=None, **kwargs):
      """Construct an instance of this Struct.

      1. With no args, the whole struct is zero-initialized.
      2. With keyword args, the matching fields are populated; rest are zeroed.
      3. With one tuple as the arg, the fields are assigned based on position.
      4. With one string arg, the Struct is parsed from bytes.
      """
      if tuple_or_bytes and kwargs:
        raise TypeError(
            "%s: cannot specify both a tuple and keyword args" % self._name)

      if tuple_or_bytes is None:
        # Default construct from null bytes.
        self._Parse("\x00" * len(self))
        # If any keywords were supplied, set those fields.
        for k, v in kwargs.iteritems():
          setattr(self, k, v)
      elif isinstance(tuple_or_bytes, str):
        # Initializing from a string.
        if len(tuple_or_bytes) < self._length:
          raise TypeError("%s requires string of length %d, got %d" %
                          (self._name, self._length, len(tuple_or_bytes)))
        self._Parse(tuple_or_bytes)
      else:
        # Initializing from a tuple.
        if len(tuple_or_bytes) != len(self._fieldnames):
          raise TypeError("%s has exactly %d fieldnames (%d given)" %
                          (self._name, len(self._fieldnames),
                           len(tuple_or_bytes)))
        self._SetValues(tuple_or_bytes)

    def _FieldIndex(self, attr):
      try:
        return self._fieldnames.index(attr)
      except ValueError:
        raise AttributeError("'%s' has no attribute '%s'" %
                             (self._name, attr))

    def __getattr__(self, name):
      return self._values[self._FieldIndex(name)]

    def __setattr__(self, name, value):
      # TODO: check value type against self._format and throw here, or else
      # callers get an unhelpful exception when they call Pack().
      self._values[self._FieldIndex(name)] = value

    def offset(self, name):
      if "." in name:
        raise NotImplementedError("offset() on nested field")
      return self._offsets[name]

    @classmethod
    def __len__(cls):
      return cls._length

    def __ne__(self, other):
      return not self.__eq__(other)

    def __eq__(self, other):
      return (isinstance(other, self.__class__) and
              self._name == other._name and
              self._fieldnames == other._fieldnames and
              self._values == other._values)

    @staticmethod
    def _MaybePackStruct(value):
      if hasattr(value, "__metaclass__"):# and value.__metaclass__ == Meta:
        return value.Pack()
      else:
        return value

    def Pack(self):
      values = [self._MaybePackStruct(v) for v in self._values]
      return struct.pack(self._format, *values)

    def __str__(self):
      def FieldDesc(index, name, value):
        if isinstance(value, str):
          if index in self._asciiz:
            value = value.rstrip("\x00")
          elif any(c not in string.printable for c in value):
            value = value.encode("hex")
        return "%s=%s" % (name, value)

      descriptions = [
          FieldDesc(i, n, v) for i, (n, v) in
          enumerate(zip(self._fieldnames, self._values))]

      return "%s(%s)" % (self._name, ", ".join(descriptions))

    def __repr__(self):
      return str(self)

    def CPointer(self):
      """Returns a C pointer to the serialized structure."""
      buf = ctypes.create_string_buffer(self.Pack())
      # Store the C buffer in the object so it doesn't get garbage collected.
      super(CStruct, self).__setattr__("_buffer", buf)
      return ctypes.addressof(self._buffer)

  return CStruct


def Read(data, struct_type):
  length = len(struct_type)
  return struct_type(data), data[length:]
