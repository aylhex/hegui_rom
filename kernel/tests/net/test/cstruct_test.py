#!/usr/bin/python
#
# Copyright 2016 The Android Open Source Project
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

import unittest

import cstruct


# These aren't constants, they're classes. So, pylint: disable=invalid-name
TestStructA = cstruct.Struct("TestStructA", "=BI", "byte1 int2")
TestStructB = cstruct.Struct("TestStructB", "=BI", "byte1 int2")


class CstructTest(unittest.TestCase):

  def CheckEquals(self, a, b):
    self.assertEquals(a, b)
    self.assertEquals(b, a)
    assert a == b
    assert b == a
    assert not (a != b)  # pylint: disable=g-comparison-negation,superfluous-parens
    assert not (b != a)  # pylint: disable=g-comparison-negation,superfluous-parens

  def CheckNotEquals(self, a, b):
    self.assertNotEquals(a, b)
    self.assertNotEquals(b, a)
    assert a != b
    assert b != a
    assert not (a == b)  # pylint: disable=g-comparison-negation,superfluous-parens
    assert not (b == a)  # pylint: disable=g-comparison-negation,superfluous-parens

  def testEqAndNe(self):
    a1 = TestStructA((1, 2))
    a2 = TestStructA((2, 3))
    a3 = TestStructA((1, 2))
    b = TestStructB((1, 2))
    self.CheckNotEquals(a1, b)
    self.CheckNotEquals(a2, b)
    self.CheckNotEquals(a1, a2)
    self.CheckNotEquals(a2, a3)
    for i in [a1, a2, a3, b]:
      self.CheckEquals(i, i)
    self.CheckEquals(a1, a3)

  def testNestedStructs(self):
    Nested = cstruct.Struct("Nested", "!HSSi",
                            "word1 nest2 nest3 int4",
                            [TestStructA, TestStructB])
    DoubleNested = cstruct.Struct("DoubleNested", "SSB",
                                  "nest1 nest2 byte3",
                                  [TestStructA, Nested])
    d = DoubleNested((TestStructA((1, 2)),
                      Nested((5, TestStructA((3, 4)), TestStructB((7, 8)), 9)),
                      6))

    expectedlen = (len(TestStructA) +
                   2 + len(TestStructA) + len(TestStructB) + 4 +
                   1)
    self.assertEquals(expectedlen, len(DoubleNested))

    self.assertEquals(7, d.nest2.nest3.byte1)

    d.byte3 = 252
    d.nest2.word1 = 33214
    n = d.nest2
    n.int4 = -55
    t = n.nest3
    t.int2 = 33627591

    self.assertEquals(33627591, d.nest2.nest3.int2)

    expected = (
        "DoubleNested(nest1=TestStructA(byte1=1, int2=2),"
        " nest2=Nested(word1=33214, nest2=TestStructA(byte1=3, int2=4),"
        " nest3=TestStructB(byte1=7, int2=33627591), int4=-55), byte3=252)")
    self.assertEquals(expected, str(d))
    expected = ("01" "02000000"
                "81be" "03" "04000000"
                "07" "c71d0102" "ffffffc9" "fc").decode("hex")
    self.assertEquals(expected, d.Pack())
    unpacked = DoubleNested(expected)
    self.CheckEquals(unpacked, d)

  def testNullTerminatedStrings(self):
    TestStruct = cstruct.Struct("TestStruct", "B16si16AH",
                                "byte1 string2 int3 ascii4 word5")
    nullstr = "hello" + (16 - len("hello")) * "\x00"

    t = TestStruct((2, nullstr, 12345, nullstr, 33210))
    expected = ("TestStruct(byte1=2, string2=68656c6c6f0000000000000000000000,"
                " int3=12345, ascii4=hello, word5=33210)")
    self.assertEquals(expected, str(t))

    embeddednull = "hello\x00visible123"
    t = TestStruct((2, embeddednull, 12345, embeddednull, 33210))
    expected = ("TestStruct(byte1=2, string2=68656c6c6f0076697369626c65313233,"
                " int3=12345, ascii4=hello\x00visible123, word5=33210)")
    self.assertEquals(expected, str(t))

  def testZeroInitialization(self):
    TestStruct = cstruct.Struct("TestStruct", "B16si16AH",
                                "byte1 string2 int3 ascii4 word5")
    t = TestStruct()
    self.assertEquals(0, t.byte1)
    self.assertEquals("\x00" * 16, t.string2)
    self.assertEquals(0, t.int3)
    self.assertEquals("\x00" * 16, t.ascii4)
    self.assertEquals(0, t.word5)
    self.assertEquals("\x00" * len(TestStruct), t.Pack())

  def testKeywordInitialization(self):
    TestStruct = cstruct.Struct("TestStruct", "=B16sIH",
                                "byte1 string2 int3 word4")
    text = "hello world! ^_^"
    text_bytes = text.encode("hex")

    # Populate all fields
    t1 = TestStruct(byte1=1, string2=text, int3=0xFEDCBA98, word4=0x1234)
    expected = ("01" + text_bytes + "98BADCFE" "3412").decode("hex")
    self.assertEquals(expected, t1.Pack())

    # Partially populated
    t1 = TestStruct(string2=text, word4=0x1234)
    expected = ("00" + text_bytes + "00000000" "3412").decode("hex")
    self.assertEquals(expected, t1.Pack())

  def testCstructOffset(self):
    TestStruct = cstruct.Struct("TestStruct", "B16si16AH",
                                "byte1 string2 int3 ascii4 word5")
    nullstr = "hello" + (16 - len("hello")) * "\x00"
    t = TestStruct((2, nullstr, 12345, nullstr, 33210))
    self.assertEquals(0, t.offset("byte1"))
    self.assertEquals(1, t.offset("string2"))  # sizeof(byte)
    self.assertEquals(17, t.offset("int3"))    # sizeof(byte) + 16*sizeof(char)
    # The integer is automatically padded by the struct module
    # to match native alignment.
    # offset = sizeof(byte) + 16*sizeof(char) + padding + sizeof(int)
    self.assertEquals(24, t.offset("ascii4"))
    self.assertEquals(40, t.offset("word5"))
    self.assertRaises(KeyError, t.offset, "random")

    # TODO: Add support for nested struct offset
    Nested = cstruct.Struct("Nested", "!HSSi", "word1 nest2 nest3 int4",
                            [TestStructA, TestStructB])
    DoubleNested = cstruct.Struct("DoubleNested", "SSB", "nest1 nest2 byte3",
                                  [TestStructA, Nested])
    d = DoubleNested((TestStructA((1, 2)), Nested((5, TestStructA((3, 4)),
                                                   TestStructB((7, 8)), 9)), 6))
    self.assertEqual(0, d.offset("nest1"))
    self.assertEqual(len(TestStructA), d.offset("nest2"))
    self.assertEqual(len(TestStructA) + len(Nested), d.offset("byte3"))
    self.assertRaises(KeyError, t.offset, "word1")

  def testDefinitionFieldMismatch(self):
    cstruct.Struct("TestA", "=BI", "byte1 int2")
    cstruct.Struct("TestA", "=BxxxxxIx", "byte1 int2")
    with self.assertRaises(ValueError):
      cstruct.Struct("TestA", "=B", "byte1 int2")
    with self.assertRaises(ValueError):
      cstruct.Struct("TestA", "=BI", "byte1")

    Nested = cstruct.Struct("Nested", "!II", "int1 int2")
    cstruct.Struct("TestB", "=BSI", "byte1 nest2 int3", [Nested])
    cstruct.Struct("TestB", "=BxSxIx", "byte1 nest2 int3", [Nested])
    with self.assertRaises(ValueError):
      cstruct.Struct("TestB", "=BSI", "byte1 int3", [Nested])
    with self.assertRaises(ValueError):
      cstruct.Struct("TestB", "=BSI", "byte1 nest2", [Nested])

    cstruct.Struct("TestC", "=BSSI", "byte1 nest2 nest3 int4", [Nested, Nested])
    with self.assertRaises(ValueError):
      cstruct.Struct("TestC", "=BSSI", "byte1 nest2 int4", [Nested, Nested])


if __name__ == "__main__":
  unittest.main()
