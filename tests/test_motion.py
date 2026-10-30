import unittest
from steambridge.motion import Motion, validate_motion
from steambridge.mapping import Mapper, validate
from test_mapping import RANGES

class MotionTests(unittest.TestCase):
    def test_old_profile_loads(self):
        self.assertTrue(validate({})['motion']['rumble'])
    def test_click_drag_and_y_inversion(self):
        m = Motion({})
        self.assertEqual(m.pad_mouse({0x122}, {18:100,19:100}), [])
        self.assertEqual(m.pad_mouse({0x122}, {18:500,19:500}), [(2,0,10),(2,1,-10)])
        m.pad_mouse(set(), {})
        self.assertEqual(m.pad_mouse({0x122}, {18:-20000,19:20000}), [])
    def test_touch_without_click_cannot_move_mouse(self):
        m = Motion({})
        self.assertEqual(m.pad_mouse(set(), {18:30000}), [])
    def test_fractional_motion_accumulates(self):
        m = Motion({})
        self.assertEqual(m.relative(.4,0), [])
        self.assertEqual(m.relative(.4,0), [])
        self.assertEqual(m.relative(.4,0), [(2,0,1)])
    def test_pad_stick_and_lift(self):
        m = Motion({'left_pad':'left-stick'})
        self.assertEqual(m.overrides(set(), {16:20000,17:1000},0), {0:20000,1:-1000})
        self.assertEqual(m.overrides(set(), {16:0,17:0},0), {})
    def test_dpad_threshold(self):
        m = Motion({'left_pad':'dpad'})
        self.assertEqual(m.overrides(set(), {16:12001,17:13000},0), {16:1,17:-1})
        self.assertEqual(m.overrides(set(), {16:1000},0), {})
    def test_gyro_mouse_timing_and_activation(self):
        m = Motion({'gyro':'mouse','gyro_sensitivity':10})
        self.assertEqual(m.gyro_frame({4:160},1,set()), [])
        self.assertEqual(m.gyro_frame({4:160},1.01,{310}), [(2,0,1)])
        self.assertEqual(m.gyro_frame({4:160},3,{310}), [])
    def test_gyro_stale_stick_releases(self):
        m = Motion({'gyro':'right-stick'})
        m.gyro_frame({4:160},1,{310})
        self.assertGreater(m.overrides({310},{},1.01)[3],0)
        self.assertEqual(m.overrides({310},{},1.2), {})
        self.assertEqual(m.overrides(set(),{},1.01), {})
    def test_gyro_bias(self):
        m = Motion({'gyro':'right-stick','gyro_bias_x':10})
        m.gyro_frame({4:160},1,{310})
        self.assertEqual(m.gyro_stick,(0,0))
    def test_gyro_reset_clears_state(self):
        m = Motion({'gyro':'right-stick'})
        m.gyro_frame({4:160},1,{310})
        m.reset()
        self.assertEqual(m.overrides({310},{},1.01), {})
    def test_output_override_restores_physical_stick(self):
        mapper = Mapper({},RANGES)
        mapper.update(3,3,10000)
        mapper.frame({3:32000})
        self.assertEqual(mapper.previous[3,3],32000)
        mapper.frame({})
        self.assertLess(mapper.previous[3,3],10000)
    def test_invalid_motion(self):
        for m in ({'gyro':'raw'}, {'rumble':1}, {'gyro_sensitivity':float('nan')},
                  {'pad_sensitivity':-1}, {'unknown':True}, {'gyro_button':'invalid'}):
            with self.subTest(m=m), self.assertRaises(ValueError):
                validate_motion(m)
