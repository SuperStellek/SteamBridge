"""Pure input mapping. Codes are Linux's public input-event ABI."""
import json
import math
from pathlib import Path

BUTTONS = {'A': 304, 'B': 305, 'X': 307, 'Y': 308, 'LB': 310,
           'RB': 311, 'Back': 314, 'Start': 315, 'Guide': 316,
           'LS': 317, 'RS': 318}
EXTRAS = {'L4': 0x224, 'R4': 0x225, 'L5': 0x226, 'R5': 0x227,
          'Left pad click': 0x121, 'Right pad click': 0x122}
DPAD = {'Up': 0x220, 'Down': 0x221, 'Left': 0x222, 'Right': 0x223}
STICKS = (0, 1, 3, 4)
TRIGGERS = {0x15: 2, 0x14: 5}  # hid-steam left/right -> X360 Z/RZ
OUTPUT_AXES = {0: (-32768, 32767), 1: (-32768, 32767),
               3: (-32768, 32767), 4: (-32768, 32767),
               2: (0, 255), 5: (0, 255), 16: (-1, 1), 17: (-1, 1)}

def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError('Profile must be a JSON object')
    if set(profile) - {'deadzone', 'bindings', 'motion'}:
        raise ValueError('Unknown profile fields')
    dz = profile.get('deadzone', 0.08)
    if isinstance(dz, bool) or not isinstance(dz, (int, float)) or not math.isfinite(dz) or not 0 <= dz <= .5:
        raise ValueError('Deadzone must be between 0 and 0.5')
    bindings = profile.get('bindings', {})
    if not isinstance(bindings, dict):
        raise ValueError('Bindings must be an object')
    for source, target in bindings.items():
        if source not in (BUTTONS | EXTRAS) or not isinstance(target, str) or target not in (BUTTONS | {'Disabled': 0}):
            raise ValueError(f'Invalid binding: {source} -> {target}')
    from .motion import validate_motion
    return {'deadzone': float(dz), 'bindings': dict(bindings),
            'motion': validate_motion(profile.get('motion', {}))}

def load_profile(path):
    return validate(json.loads(Path(path).read_text())) if path else validate({})

def scale(value, low, high, out_low, out_high):
    if high <= low:
        raise ValueError('Invalid input axis range')
    fraction = max(0., min(1., (value-low)/(high-low)))
    return round(out_low + fraction*(out_high-out_low))

class Mapper:
    def __init__(self, profile, ranges):
        self.profile = validate(profile)
        self.ranges = ranges
        self.keys = set()
        self.axes = {}
        self.previous = {}
        self.bindings = {code: BUTTONS.get(self.profile['bindings'].get(name, name))
                         for name, code in (BUTTONS | EXTRAS).items()}

    def update(self, kind, code, value):
        if kind == 1:
            if value:
                self.keys.add(code)
            else:
                self.keys.discard(code)
        elif kind == 3:
            self.axes[code] = value

    def snapshot(self, keys, axes):
        self.keys = set(keys)
        self.axes = dict(axes)

    def frame(self, overrides=None):
        # Aggregate before emitting: releasing a paddle must not release a held A.
        pressed = {self.bindings.get(k) for k in self.keys}
        state = {(1, code): int(code in pressed) for code in BUTTONS.values()}
        state[3, 16] = int(DPAD['Right'] in self.keys)-int(DPAD['Left'] in self.keys)
        state[3, 17] = int(DPAD['Down'] in self.keys)-int(DPAD['Up'] in self.keys)
        for code in STICKS:
            low, high = self.ranges[code]
            value = self.axes.get(code, 0)
            # Signed axes use zero as their physical centre, including asymmetric ranges.
            n = max(-1., min(1., value/(high if value >= 0 else -low)))
            dz = self.profile['deadzone']
            n = 0 if abs(n) <= dz else math.copysign((abs(n)-dz)/(1-dz), n)
            state[3, code] = round(n*(32767 if n >= 0 else 32768))
        for source, target in TRIGGERS.items():
            low, high = self.ranges[source]
            state[3, target] = scale(self.axes.get(source, low), low, high, 0, 255)
        for code, value in (overrides or {}).items():
            state[3, code] = value
        changed = [(kind, code, value) for (kind, code), value in state.items()
                   if self.previous.get((kind, code)) != value]
        self.previous = state
        return changed
