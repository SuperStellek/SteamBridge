from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from steambridge.backend import candidates, Session, run
from test_mapping import RANGES

class FakeDevice:
    path = '/dev/input/event42'
    def __init__(self):
        self.grabbed = False
        self.closed = False
        self.events = []
        self.keys = []
    ff_effects_count = 0
    def capabilities(self, absinfo=False): return {1: [304], 3: list(RANGES)}
    def absinfo(self, code):
        low, high = RANGES[code]
        return SimpleNamespace(min=low,max=high,value=0)
    def active_keys(self): return self.keys
    def grab(self): self.grabbed = True
    def ungrab(self): self.grabbed = False
    def close(self): self.closed = True
    def read(self): return iter(self.events)

class FakeUI:
    def __init__(self, *args, **kwargs):
        self.events = []
        self.closed = False
    def write(self, *event): self.events.append(event)
    def syn(self): pass
    def close(self): self.closed = True

FAKE_EVDEV = SimpleNamespace(UInput=FakeUI, AbsInfo=lambda *args: args)

class BackendTests(unittest.TestCase):
    def test_filter_exact_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, vendor, product in [('event1','28de','1303'), ('event2','045e','028e'),
                                          ('event3','28de','1102'), ('event4','28de','1304')]:
                ids = root/name/'device/id'
                ids.mkdir(parents=True)
                (ids/'vendor').write_text(vendor)
                (ids/'product').write_text(product)
            self.assertEqual(list(candidates(root)), ['/dev/input/event1','/dev/input/event4'])

    def test_cleanup(self):
        dev = FakeDevice()
        session = Session(dev, {}, FAKE_EVDEV)
        ui = session.ui
        self.assertTrue(dev.grabbed)
        session.close()
        self.assertFalse(dev.grabbed)
        self.assertTrue(dev.closed)
        self.assertTrue(ui.closed)

    def test_creation_failure_releases_grab(self):
        dev = FakeDevice()
        def fail(*args, **kwargs): raise PermissionError('uinput')
        with self.assertRaises(PermissionError):
            Session(dev, {}, SimpleNamespace(UInput=fail,AbsInfo=lambda *args: args))
        self.assertFalse(dev.grabbed)
        self.assertTrue(dev.closed)

    def test_dropped_events_resync(self):
        dev = FakeDevice()
        s = Session(dev, {}, FAKE_EVDEV)
        event = lambda t,c,v: SimpleNamespace(type=t,code=c,value=v)
        dev.events = [event(1,304,1),event(0,0,0)]
        s.read()
        self.assertEqual(s.mapper.previous[1,304],1)
        # An unreliable press after SYN_DROPPED must be ignored.
        dev.events = [event(0,3,0), event(1,305,1), event(0,0,0)]
        s.read()
        self.assertEqual(s.mapper.previous[1,304],0)
        self.assertEqual(s.mapper.previous[1,305],0)
        s.close()

    def test_steam_pause_never_opens_devices(self):
        class Stop:
            done = False
            def is_set(self): return self.done
            def wait(self, _): self.done = True
        messages = []
        with patch.dict('sys.modules', {'evdev': FAKE_EVDEV}), \
             patch('steambridge.backend.lock_instance', return_value=123), \
             patch('steambridge.backend.os.close') as close, \
             patch('steambridge.backend.steam_running', return_value=True), \
             patch('steambridge.backend.candidates') as discover:
            run(Stop(), {}, messages.append)
            discover.assert_not_called()
            close.assert_called_once_with(123)
        self.assertTrue(messages[0].startswith('Paused'))

if __name__ == '__main__':
    unittest.main()

class IntegrationTests(unittest.TestCase):
    def test_rumble_advertised_only_when_available(self):
        created = []
        class UI(FakeUI):
            def __init__(self, caps, **kw):
                super().__init__()
                self.caps, self.kw = caps, kw
                created.append(self)
        class FFDevice(FakeDevice):
            ff_effects_count = 4
            def capabilities(self, absinfo=False):
                return {1:[304], 3:list(RANGES), 21:[0x50]}
        dev = FFDevice()
        s = Session(dev, {'motion':{'right_pad':'off'}}, SimpleNamespace(UInput=UI,AbsInfo=lambda *x:x))
        self.assertEqual(s.ui.caps[21], [0x50])
        self.assertEqual(s.ui.kw['max_effects'],4)
        self.assertIsNotNone(s.rumble)
        s.close()
        s = Session(FakeDevice(), {'motion':{'right_pad':'off'}}, SimpleNamespace(UInput=UI,AbsInfo=lambda *x:x))
        self.assertNotIn(21,s.ui.caps)
        s.close()

    def test_sensor_pairs_to_same_hid_parent(self):
        class Sensor(FakeDevice):
            def capabilities(self, absinfo=False): return {3:[0,1,2,3,4,5],4:[5]}
            def absinfo(self,c): return SimpleNamespace(value=0)
        opened = []
        sensor = Sensor()
        sensor.path = '/dev/input/event43'
        def open_device(path):
            opened.append(path)
            return sensor
        evdev = SimpleNamespace(UInput=FakeUI,AbsInfo=lambda *x:x,InputDevice=open_device)
        s = Session(FakeDevice(), {'motion':{'gyro':'mouse'}}, evdev)
        with patch('steambridge.backend.device_parent', side_effect=lambda p: 'other' if p.endswith('99') else 'same'):
            s.attach_sensor(['/dev/input/event99','/dev/input/event43'])
        self.assertEqual(opened,['/dev/input/event43'])
        self.assertIs(s.sensor,sensor)
        s.close()
        self.assertTrue(sensor.closed)

    def test_sensor_drop_resets_gyro_output(self):
        class Sensor(FakeDevice):
            def absinfo(self,c): return SimpleNamespace(value=0)
        s = Session(FakeDevice(), {'motion':{'gyro':'right-stick'}}, FAKE_EVDEV)
        s.sensor = Sensor()
        s.motion.gyro_frame({4:160},1,{310})
        s.sensor.events = [SimpleNamespace(type=0,code=3,value=0),SimpleNamespace(type=0,code=0,value=0)]
        s.read_sensor()
        self.assertEqual(s.motion.gyro_stick,(0,0))
        self.assertFalse(s.sensor_dropped)
        s.close()
