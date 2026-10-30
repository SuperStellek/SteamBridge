import math
import unittest
from steambridge.mapping import Mapper, validate, scale, BUTTONS, EXTRAS, DPAD

RANGES = {0: (-32767,32767), 1: (-32767,32767), 3: (-32767,32767),
          4: (-32767,32767), 20: (0,32767), 21: (0,32767)}

class MappingTests(unittest.TestCase):
    def make(self, profile=None):
        return Mapper(profile or {}, RANGES)

    def test_rest(self):
        m = self.make()
        self.assertTrue(all(value == 0 for _, _, value in m.frame()))
        self.assertEqual(m.frame(), [])

    def test_endpoints(self):
        m = self.make()
        m.update(3, 0, -32767)
        m.update(3, 3, 32767)
        m.frame()
        self.assertEqual(m.previous[3,0], -32768)
        self.assertEqual(m.previous[3,3], 32767)

    def test_deadzone(self):
        m = self.make({'deadzone': .1})
        m.update(3, 0, 2000)
        m.frame()
        self.assertEqual(m.previous[3,0], 0)
        m.update(3, 0, 18022)
        m.frame()
        self.assertAlmostEqual(m.previous[3,0], 16383, delta=3)

    def test_trigger_sides(self):
        m = self.make()
        m.update(3, 21, 32767)
        m.update(3, 20, 16384)
        m.frame()
        self.assertEqual(m.previous[3,2], 255)
        self.assertEqual(m.previous[3,5], 128)

    def test_overlap_release(self):
        m = self.make({'bindings': {'L4': 'A'}})
        m.update(1, BUTTONS['A'], 1)
        m.update(1, EXTRAS['L4'], 1)
        m.frame()
        m.update(1, EXTRAS['L4'], 0)
        self.assertEqual(m.frame(), [])
        m.update(1, BUTTONS['A'], 0)
        self.assertEqual(m.frame(), [(1, 304, 0)])

    def test_opposing_dpad(self):
        m = self.make()
        for name in ('Left', 'Right'):
            m.update(1, DPAD[name], 1)
        m.frame()
        self.assertEqual(m.previous[3,16], 0)
        m.update(1, DPAD['Left'], 0)
        self.assertEqual(m.frame(), [(3,16,1)])

    def test_disabled_and_remapped(self):
        m = self.make({'bindings': {'A': 'Disabled', 'B': 'X'}})
        m.update(1, 304, 1)
        m.update(1, 305, 1)
        m.frame()
        self.assertEqual(m.previous[1,304], 0)
        self.assertEqual(m.previous[1,305], 0)
        self.assertEqual(m.previous[1,307], 1)

    def test_resync_clears_held_buttons(self):
        m = self.make()
        m.update(1, 304, 1)
        m.frame()
        m.snapshot([], {})
        self.assertIn((1,304,0), m.frame())

    def test_no_pad_motion_leaks_to_dpad(self):
        m = self.make()
        m.update(3, 16, 30000)
        m.frame()
        self.assertEqual(m.previous[3,16], 0)

    def test_invalid_profiles(self):
        for data in ([], {'deadzone': math.nan}, {'deadzone': True}, {'deadzone': 1},
                     {'deadzone': '10'}, {'bindings': []}, {'bindings': {'L4':'shell'}},
                     {'bindings': {'fake': 'A'}}, {'bindings': {'A': []}}, {'unknown': 1}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate(data)

    def test_clamping(self):
        self.assertEqual(scale(-1, 0, 100, 0, 255), 0)
        self.assertEqual(scale(999, 0, 100, 0, 255), 255)
        with self.assertRaises(ValueError):
            scale(0,0,0,0,255)

if __name__ == '__main__':
    unittest.main()
