import fcntl
import os
from pathlib import Path
import select
import time

from .mapping import Mapper, BUTTONS, OUTPUT_AXES, STICKS, TRIGGERS
from .motion import Motion
from .rumble import Rumble

PRODUCTS = {0x1302, 0x1303, 0x1304, 0x1305}
REQUIRED = set(STICKS) | set(TRIGGERS)

def candidates(root=Path('/sys/class/input')):
    for event in sorted(root.glob('event*')):
        try:
            ids = event / 'device/id'
            if int((ids/'vendor').read_text(), 16) == 0x28de and int((ids/'product').read_text(), 16) in PRODUCTS:
                yield '/dev/input/' + event.name
        except (OSError, ValueError):
            continue

def steam_running(root=Path('/proc')):
    for proc in root.glob('[0-9]*'):
        try:
            if proc.stat().st_uid == os.getuid() and (proc/'comm').read_text().strip() == 'steam':
                return True
        except OSError:
            continue
    return False

def lock_instance():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('XDG_RUNTIME_DIR is missing. Run from your logged-in desktop session.')
    fd = os.open(Path(runtime)/'steambridge.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError('SteamBridge is already running. Stop the other window or user service.')
    return fd

class Session:
    def __init__(self, dev, profile, evdev):
        self.dev, self.ui, self.grabbed = dev, None, False
        self.dropped = False
        self.sensor = None
        self.sensor_dropped = False
        self.sensor_axes = {}
        self.mouse = None
        self.rumble = None
        self.evdev = evdev
        self.motion = Motion(profile.get('motion', {}))
        self.axis_codes = REQUIRED | (set(dev.capabilities(absinfo=False).get(3, [])) & {16, 17, 18, 19})
        try:
            ranges = {c: (dev.absinfo(c).min, dev.absinfo(c).max) for c in REQUIRED}
            if any(lo >= 0 or hi <= 0 for c, (lo, hi) in ranges.items() if c in STICKS):
                raise ValueError('Unexpected stick axis ranges')
            if any(lo >= hi for lo, hi in ranges.values()):
                raise ValueError('Unexpected axis ranges')
            self.mapper = Mapper(profile, ranges)
            caps = {1: list(BUTTONS.values()), 3: [
                (c, evdev.AbsInfo(0, lo, hi, 0, 0, 0)) for c, (lo, hi) in OUTPUT_AXES.items()]}
            supported_ff = 0x50 in dev.capabilities(absinfo=False).get(21, [])
            enable_ff = self.motion.settings['rumble'] and supported_ff and dev.ff_effects_count > 0
            if enable_ff:
                caps[21] = [0x50]
            dev.grab()
            self.grabbed = True
            self.ui = evdev.UInput(caps, name='Microsoft X-Box 360 pad',
                                  vendor=0x045e, product=0x028e, version=0x0114, bustype=3,
                                  max_effects=dev.ff_effects_count if enable_ff else 0)
            if enable_ff:
                self.rumble = Rumble(dev, self.ui)
            if any(self.motion.settings[k] == 'mouse' for k in ('left_pad', 'right_pad', 'gyro')):
                self.mouse = evdev.UInput({2: [0, 1], 1: [272, 273]},
                                         name='SteamBridge Motion Mouse', vendor=0x1209, product=0x5342)
            self.resync()
        except Exception:
            self.close()
            raise

    def resync(self):
        self.motion.reset()
        self.mapper.snapshot(self.dev.active_keys(), {c: self.dev.absinfo(c).value for c in self.axis_codes})
        self.emit()

    def emit(self):
        for event in self.mapper.frame(self.motion.overrides(self.mapper.keys, self.mapper.axes, time.monotonic())):
            self.ui.write(*event)
        self.ui.syn()
        self.mouse_events(self.motion.pad_mouse(self.mapper.keys, self.mapper.axes))

    def mouse_events(self, events):
        if self.mouse and events:
            for event in events:
                self.mouse.write(*event)
            self.mouse.syn()

    def attach_sensor(self, paths):
        if self.motion.settings['gyro'] == 'off' or self.sensor is not None:
            return
        for path in paths:
            if path == self.dev.path or device_parent(path) != device_parent(self.dev.path):
                continue
            sensor = self.evdev.InputDevice(path)
            caps = sensor.capabilities(absinfo=False)
            if {3, 4, 5} <= set(caps.get(3, [])) and 304 not in caps.get(1, []) and 5 in caps.get(4, []):
                self.sensor = sensor
                self.sensor_axes = {c: sensor.absinfo(c).value for c in (3, 4, 5)}
                self.motion.reset()
                return
            sensor.close()

    def read_sensor(self):
        try:
            for event in self.sensor.read():
                if event.type == 0 and event.code == 3:
                    self.sensor_dropped = True
                    self.motion.reset()
                elif event.type == 0 and event.code == 0:
                    if self.sensor_dropped:
                        self.sensor_axes = {c: self.sensor.absinfo(c).value for c in (3, 4, 5)}
                        self.sensor_dropped = False
                        self.motion.reset()
                    else:
                        self.mouse_events(self.motion.gyro_frame(self.sensor_axes, event.timestamp(), self.mapper.keys, time.monotonic()))
                    self.emit()
                elif not self.sensor_dropped and event.type == 3:
                    self.sensor_axes[event.code] = event.value
        except BlockingIOError:
            pass

    def sources(self):
        result = [(self.dev, self.read)]
        if self.sensor is not None:
            result.append((self.sensor, self.read_sensor))
        if self.rumble is not None:
            result.append((self.ui, self.rumble.read))
        return result

    def read(self):
        try:
            events = self.dev.read()
            for event in events:
                if event.type == 0 and event.code == 3:  # SYN_DROPPED
                    self.dropped = True
                elif event.type == 0 and event.code == 0:
                    if self.dropped:
                        self.resync()
                        self.dropped = False
                    else:
                        self.emit()
                elif not self.dropped:
                    self.mapper.update(event.type, event.code, event.value)
        except BlockingIOError:
            pass

    def close(self):
        if self.rumble is not None:
            self.rumble.close()
            self.rumble = None
        if self.sensor is not None:
            self.sensor.close()
            self.sensor = None
        if self.mouse is not None:
            self.mouse.close()
            self.mouse = None
        try:
            if self.ui is not None:
                self.ui.close()  # Destroy virtual device, including held state.
        finally:
            self.ui = None
            if self.grabbed:
                try:
                    self.dev.ungrab()
                except OSError:
                    pass
                self.grabbed = False
            self.dev.close()

def device_parent(path):
    # Both gamepad and IMU input devices belong to the same physical HID interface.
    return (Path('/sys/class/input') / Path(path).name / 'device').resolve().parent.parent

def run(stop, profile, report=print):
    import evdev
    fd = lock_instance()
    sessions = {}
    last_scan = 0
    last_status = None
    def status(message):
        nonlocal last_status
        if message != last_status:
            report(message)
            last_status = message
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now-last_scan >= 1:
                last_scan = now
                if steam_running():
                    for session in sessions.values():
                        session.close()
                    sessions.clear()
                    status('Paused: Steam is running. Exit Steam to use the bridge.')
                    stop.wait(.25)
                    continue
                found = set(candidates())
                for path in list(sessions):
                    if path not in found:
                        sessions.pop(path).close()
                errors = []
                for path in found-sessions.keys():
                    dev = None
                    try:
                        dev = evdev.InputDevice(path)
                        caps = dev.capabilities(absinfo=False)
                        if not REQUIRED <= set(caps.get(3, [])) or 304 not in caps.get(1, []):
                            dev.close()
                            continue  # Ignore keyboard, mouse and IMU nodes.
                        sessions[path] = Session(dev, profile, evdev)
                    except (OSError, ValueError) as exc:
                        if dev is not None:
                            dev.close()
                        errors.append(f'{path}: {exc}')
                for session in sessions.values():
                    try:
                        session.attach_sensor(found)
                    except OSError as exc:
                        errors.append(f'Gyro unavailable: {exc}')
                if errors:
                    status('Device access error: ' + '; '.join(errors))
                elif sessions:
                    status(f'Active: {len(sessions)} pad(s); gyro sensors: {sum(s.sensor is not None for s in sessions.values())}; rumble: {sum(s.rumble is not None for s in sessions.values())}.')
                else:
                    status('Waiting for a controller. If connected, run Diagnostics and check hid-steam support.')
            if sessions:
                sources = {source.fd: (session, callback) for session in sessions.values()
                           for source, callback in session.sources()}
                ready, _, _ = select.select(list(sources), [], [], .02)
                for source in ready:
                    session, callback = sources[source]
                    if session.dev.path not in sessions:
                        continue
                    try:
                        callback()
                    except OSError as exc:
                        sessions.pop(session.dev.path).close()
                        status(f'Disconnected or output error: {exc}')
                # Clear stale gyro stick output even if the sensor stops reporting.
                for session in sessions.values():
                    if session.motion.settings['gyro'] == 'right-stick':
                        session.emit()
            else:
                stop.wait(.1)
    finally:
        for session in sessions.values():
            session.close()
        os.close(fd)
        report('Stopped. Physical controller released.')

def diagnostics():
    import platform
    import evdev
    lines = [f'Kernel: {platform.release()}', f'Steam running: {steam_running()}',
             f'uinput writable: {os.access("/dev/uinput", os.W_OK)}']
    paths = list(candidates())
    for path in paths:
        dev = None
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities(absinfo=False)
            supported = REQUIRED <= set(caps.get(3, [])) and 304 in caps.get(1, [])
            lines.append(f'{path}: {dev.name}; gamepad: {supported}; rumble: {0x50 in caps.get(21, [])}; gyro: {5 in caps.get(4, []) and {3,4,5} <= set(caps.get(3, []))}')
        except OSError as exc:
            lines.append(f'{path}: {exc}')
        finally:
            if dev is not None:
                dev.close()
    if not paths:
        lines.append('No 2026 controller event nodes. Connect/pair it, exit Steam, and check your kernel driver.')
    lines.append('Required: hid-steam with 28de:1302/1303/1304/1305 support; uinput; local session device ACLs.')
    return '\n'.join(lines)
