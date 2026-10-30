"""Motion processing independent of Linux device I/O."""
import math

PADS = {'left': (16, 17, 0x121), 'right': (18, 19, 0x122)}
DEFAULT_MOTION = {'left_pad': 'off', 'right_pad': 'mouse', 'pad_sensitivity': .025,
                  'gyro': 'off', 'gyro_sensitivity': 12., 'gyro_button': 'LB',
                  'gyro_deadzone': .5, 'gyro_bias_x': 0., 'gyro_bias_y': 0.,
                  'invert_gyro_y': False, 'rumble': True}

def validate_motion(value):
    from .mapping import BUTTONS, EXTRAS
    if not isinstance(value, dict) or set(value)-set(DEFAULT_MOTION):
        raise ValueError('Unknown motion settings')
    m = DEFAULT_MOTION | value
    for key in ('left_pad', 'right_pad'):
        if m[key] not in ('off', 'mouse', 'left-stick', 'right-stick', 'dpad'):
            raise ValueError('Invalid trackpad mode')
    if m['gyro'] not in ('off', 'mouse', 'right-stick'):
        raise ValueError('Invalid gyro mode')
    if m['gyro_button'] not in (*BUTTONS, *EXTRAS, 'Always'):
        raise ValueError('Invalid gyro activation button')
    for key, low, high in [('pad_sensitivity', .001, 1), ('gyro_sensitivity', .1, 100),
                           ('gyro_deadzone', 0, 20), ('gyro_bias_x', -100, 100),
                           ('gyro_bias_y', -100, 100)]:
        n = m[key]
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not low <= n <= high:
            raise ValueError(f'Invalid {key}: expected {low} to {high}')
    for key in ('invert_gyro_y', 'rumble'):
        if not isinstance(m[key], bool):
            raise ValueError(f'{key} must be boolean')
    return m

class Motion:
    def __init__(self, settings):
        self.settings = validate_motion(settings)
        self.previous_pad = {}
        self.remainder = [0., 0.]
        self.last_time = None
        self.gyro_stick = (0, 0)
        self.sensor_seen = None

    def reset(self):
        self.previous_pad.clear()
        self.remainder = [0., 0.]
        self.last_time = None
        self.gyro_stick = (0, 0)
        self.sensor_seen = None

    def relative(self, x, y):
        result = []
        for axis, value in enumerate((x, y)):
            self.remainder[axis] += value
            whole = math.trunc(self.remainder[axis])
            self.remainder[axis] -= whole
            if whole:
                result.append((2, axis, whole))
        return result

    def pad_mouse(self, keys, axes):
        result = []
        for side, (x, y, click) in PADS.items():
            # hid-steam does not expose IBEX touch flags. Click-drag is unambiguous.
            if self.settings[side+'_pad'] != 'mouse' or click not in keys:
                self.previous_pad.pop(side, None)
                continue
            current = (axes.get(x, 0), axes.get(y, 0))
            previous = self.previous_pad.get(side)
            self.previous_pad[side] = current
            if previous is not None:
                gain = self.settings['pad_sensitivity']
                result += self.relative((current[0]-previous[0])*gain, -(current[1]-previous[1])*gain)
        return result

    def active(self, keys):
        from .mapping import BUTTONS, EXTRAS
        name = self.settings['gyro_button']
        return name == 'Always' or (BUTTONS | EXTRAS)[name] in keys

    def gyro_frame(self, axes, timestamp, keys, now=None):
        previous, self.last_time = self.last_time, timestamp
        self.sensor_seen = timestamp if now is None else now
        self.gyro_stick = (0, 0)
        if self.settings['gyro'] == 'off' or not self.active(keys):
            self.remainder = [0., 0.]
            return []
        # hid-steam's ABI has 16 counts per degree/second. RY is yaw, RX pitch.
        x = axes.get(4, 0)/16-self.settings['gyro_bias_x']
        y = axes.get(3, 0)/16-self.settings['gyro_bias_y']
        x = x if abs(x) >= self.settings['gyro_deadzone'] else 0
        y = y if abs(y) >= self.settings['gyro_deadzone'] else 0
        if self.settings['invert_gyro_y']:
            y = -y
        gain = self.settings['gyro_sensitivity']
        if self.settings['gyro'] == 'right-stick':
            self.gyro_stick = tuple(round(max(-32768, min(32767, v*gain*128))) for v in (x, y))
            return []
        if previous is None or not 0 < timestamp-previous <= .05:
            return []  # Do not integrate across reconnects, drops or long stalls.
        return self.relative(x*gain*(timestamp-previous), y*gain*(timestamp-previous))

    def overrides(self, keys, axes, now):
        result = {}
        for side, (x, y, _) in PADS.items():
            mode = self.settings[side+'_pad']
            px, py = axes.get(x, 0), -axes.get(y, 0)
            if mode in ('left-stick', 'right-stick') and (px or py):
                base = 0 if mode == 'left-stick' else 3
                result[base] = max(-32768, min(32767, px))
                result[base+1] = max(-32768, min(32767, py))
            elif mode == 'dpad':
                for out, value in ((16, px), (17, py)):
                    direction = (1 if value > 12000 else -1 if value < -12000 else 0)
                    if direction:
                        result[out] = direction
        if self.settings['gyro'] == 'right-stick' and self.active(keys) and self.sensor_seen is not None and 0 <= now-self.sensor_seen < .1:
            for axis, value in zip((3, 4), self.gyro_stick):
                if value:
                    result[axis] = value
        return result
