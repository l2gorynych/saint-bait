import struct
import unittest
from saint_bait.telemetry.transforms import world_position
from saint_bait.telemetry.transforms import world_pose,view_angles


class TransformTests(unittest.TestCase):
    def reader(self,parent=-1):
        memory=bytearray(4096)
        struct.pack_into('<Q',memory,116,200)
        struct.pack_into('<Q',memory,256,300)
        struct.pack_into('<i',memory,264,0)
        struct.pack_into('<QQ',memory,324,500,700)
        struct.pack_into('<12f',memory,500,1,2,3,0,0,0,0,1,1,1,1,0)
        struct.pack_into('<i',memory,700,parent)
        class Reader:
            def read(self,address,size):return bytes(memory[address:address+size])
            def ptr(self,address):return struct.unpack('<Q',self.read(address,8))[0]
        return Reader(),memory

    def test_root_and_scaled_parent_position(self):
        reader,memory=self.reader()
        self.assertEqual(world_position(reader,100),(1.,2.,3.))
        struct.pack_into('<i',memory,700,1)
        struct.pack_into('<12f',memory,548,10,20,30,0,0,0,0,1,2,2,2,0)
        struct.pack_into('<i',memory,704,-1)
        self.assertEqual(world_position(reader,100),(12.,24.,36.))

    def test_invalid_or_cyclic_parents_are_rejected(self):
        for parent in (0,100000,-2):
            reader,_=self.reader(parent)
            with self.assertRaises(ValueError):world_position(reader,100)

    def test_world_rotation_includes_parent_heading(self):
        reader,memory=self.reader(1)
        struct.pack_into('<12f',memory,548,10,20,30,0,0,2**-.5,0,2**-.5,1,1,1,0)
        struct.pack_into('<i',memory,704,-1)
        position,rotation=world_pose(reader,100)
        yaw,pitch=view_angles(rotation)
        self.assertAlmostEqual(yaw,90.,places=4)
        self.assertAlmostEqual(pitch,0.,places=4)
        for actual,expected in zip(position,(13.,22.,29.)):self.assertAlmostEqual(actual,expected,places=4)
