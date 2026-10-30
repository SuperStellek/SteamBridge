# SteamBridge for Arch Linux

An experimental native desktop app (version 0.2.0) that translates the **2026 Steam Controller**
into an Xbox 360-style Linux virtual gamepad for games outside Steam. This is an
independent implementation, not an official port of SteamlessController or a Valve product.

**Hardware testing is still required.** The mapping and lifecycle tests run without
hardware; this release has not been validated on a physical controller or an Arch desktop.
It is supplied as source with a local Arch PKGBUILD, not a prebuilt signed package.

## New in 0.2.0

- Gyro aiming as mouse movement or right-stick output, with a hold-to-aim button,
  sensitivity, deadzone, Y inversion and optional saved bias corrections.
- Both trackpads can output mouse motion, left stick, right stick or D-pad.
- Game rumble is forwarded through Linux force feedback, including effect
  uploads, updates, playback, stop and erase. Requires physical FF_RUMBLE support.
- Motion settings are editable in the desktop window and saved in profiles.

Gyro defaults to **off** so picking up a controller does not unexpectedly move
the pointer. Enable it in Motion and rumble; the default hold-to-aim button is
**LB**. Right trackpad defaults to **mouse**: hold the pad click while sliding.
Left trackpad defaults to off. Rumble defaults to enabled where supported.

## Requirements and compatibility

- Arch Linux with a `hid-steam` driver that includes the **2026 / IBEX** controller.
  Upstream Linux source includes this support, but your installed kernel must actually
  have it. A kernel version number alone is not used as a compatibility check.
- USB `28de:1302`, Bluetooth `28de:1303`, puck `28de:1304`, or receiver `28de:1305`.
  These are eligible only when the kernel exposes the expected gamepad interface.
- A local logged-in desktop session, Python 3.10+, python-evdev, Tk, and `/dev/uinput`.
- Gyro additionally needs the kernel's matching Motion Sensors evdev node.
- Rumble additionally needs the kernel's `CONFIG_STEAM_FF` functionality and an
  evdev interface advertising FF_RUMBLE. The app reports available sensors and
  rumble-enabled controllers; missing support is not emulated with guessed HID writes.
- Exit Steam while using the bridge. It automatically pauses when your user's
  `steam` process is detected and resumes after Steam exits (about one second).

If your kernel already exposes a usable gamepad and the game recognizes it,
you may not need this app. SteamBridge adds an Xbox-style identity and remapping.
It does not implement a raw-HID fallback for older kernels. If the controller
only appears as a keyboard/mouse, update your system/kernel before proceeding.

## Install on Arch

Clone the repository (install `git` first if needed), then enter its directory:

```sh
git clone https://github.com/SuperStellek/SteamBridge.git
cd SteamBridge
```

Alternatively, extract the source archive and enter its `steambridge` directory.
Then run:

```sh
sudo pacman -Syu --needed base-devel python-build python-installer python-setuptools python-wheel python-evdev tk
makepkg -si
sudo modprobe uinput
sudo modprobe joydev
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --sysname-match=uinput
```

Unplug/replug the controller or puck (reconnect Bluetooth). If access is still
denied, log out and back in. Launch **SteamBridge** from your application menu or:

```sh
steambridge
```

Select **Start bridge**, wait for **Active**, then start your non-Steam game,
emulator, Lutris game, or Wine game. The game must support Linux gamepads or
Wine's controller translation. Games and sandboxed launchers vary; compatibility
with every game is not guaranteed. Start the bridge before the game so it can
discover the virtual device.

The permission rules grant the active local user access to the relevant Valve
event nodes and uinput. The app runs as your user, never as root. Do not use
`chmod 666` or add yourself to the broad `input` group to troubleshoot this app.

## Controls and profiles

- A/B/X/Y, shoulders, menu/view/guide, stick clicks, both sticks and analog triggers.
- Physical D-pad converted to a standard Xbox hat.
- Remap buttons, four rear grips, and trackpad clicks to gamepad buttons.
- Adjustable stick deadzone; JSON profiles load/save through the window.
- A source mapped to Disabled produces no output. Extra buttons default to Disabled.
- Stop and restart the bridge after changing a mapping or loading a profile.
- Multiple eligible controllers receive independent virtual pads with the same profile.

Example profile:

```json
{
  "deadzone": 0.08,
  "bindings": {"L4": "X", "R4": "A", "L5": "LB", "R5": "RB"}
}
```

The L4/R4/L5/R5 labels correspond to Linux BTN_GRIPL/GRIPR/GRIPL2/GRIPR2.
Confirm their physical positions with your firmware. Triggers map from the
kernel's ABS_HAT2Y (left) and ABS_HAT2X (right); stick orientation is already
corrected by hid-steam and is not inverted again.

## Motion profiles

Old profiles still load. An additional optional `motion` object stores settings:

```json
{
  "deadzone": 0.08,
  "bindings": {"R4": "Disabled"},
  "motion": {
    "left_pad": "dpad",
    "right_pad": "mouse",
    "pad_sensitivity": 0.025,
    "gyro": "mouse",
    "gyro_button": "R4",
    "gyro_sensitivity": 12,
    "gyro_deadzone": 0.5,
    "gyro_bias_x": 0,
    "gyro_bias_y": 0,
    "invert_gyro_y": false,
    "rumble": true
  }
}
```

Mouse gyro sensitivity is pixels per degree; right-stick mode uses an independent
rate-to-stick scale (sensitivity × 128 counts per degree/second). Gyro bias values
are degrees/second subtracted from stationary yaw and pitch, editable in JSON if
needed. There is no automatic calibration; start with a small deadzone. Sensor
pairing uses the physical HID parent, never the first connected controller.

## Headless mode and optional autostart

```sh
steambridge --diagnose
steambridge --headless --profile /absolute/path/to/profile.json
```

Ctrl+C cleanly releases the device. The desktop window and headless mode use the
same per-user lock, so do not run both at once.

For optional default-profile autostart:

```sh
systemctl --user daemon-reload
systemctl --user enable --now steambridge.service
journalctl --user -u steambridge.service -f
```

This requires a desktop that manages `graphical-session.target`. If yours does
not, launch the GUI manually. Stop the service before using the GUI:

```sh
systemctl --user disable --now steambridge.service
```

For a service profile, use `systemctl --user edit steambridge.service` and set:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/steambridge --headless --profile /absolute/path/to/profile.json
```

## Diagnostics and known limits

The Diagnostics button prints kernel, uinput access, and detected Valve input
interfaces. It does not collect keyboard events or upload any information.

- **No eligible gamepad:** exit Steam, connect the controller, and run
  `steambridge --diagnose`, `uname -r`, and `modinfo hid_steam`. Check that
  module aliases include the 2026 product IDs. Arch's LTS kernel may lack them.
- **Permission denied:** check the installed udev rules and active local session;
  replug the controller and log out/in. Do not launch the GUI with sudo.
- **Device busy:** stop other remappers and any other SteamBridge instance.
- **Input stops when Steam launches:** intentional. Close Steam to resume.
  Process detection is best-effort and is not an atomic ownership handshake.
- **Double input:** the app grabs the physical evdev gamepad; it does not hide
  hidraw devices from games using their own raw-HID drivers. Such games may need
  their raw-HID controller path disabled or their normal kernel controller path used.
- **Flatpak game cannot see it:** its sandbox must permit controller devices.
- **Touch gestures, general keyboard/mouse button bindings, per-game auto-selection,
  tray icon, and PlayStation emulation are not implemented.** Gyro and pad mouse
  modes emit relative motion, not a native game-visible IMU or PlayStation touchpad.
- The current kernel IBEX interface does not expose separate pad-touch flags.
  Mouse mode therefore requires holding the pad click; tap gestures and touch-only
  mouse dragging cannot be reliably implemented through this interface.
- Trackpad stick mode overrides the selected stick while coordinates are nonzero;
  returning to the centre or lifting restores the physical stick. Pad Y is inverted
  from raw coordinates. D-pad mode activates past a 12000-count threshold.
- Gyro right-stick output overrides its nonzero axes, then pad output takes
  precedence over physical sticks. Stale gyro output expires after 100 ms.
- Some games do not accept simultaneous mouse and gamepad input. Use gyro
  right-stick mode in those games. Wayland/X11 pointer speed can affect mouse output.
- Hold-to-aim does not consume the selected button: it retains its normal mapping.
  Use a rear button mapped to Disabled if you want an activation-only control.
- Closing the window stops the bridge. It does not minimize to a tray.
- This app does not modify firmware, Bluetooth pairing, kernel bindings, or Steam files.

## Development and validation

```sh
python -m unittest discover -s tests -v
python -m compileall -q steambridge
python -m steambridge --help
```

The tests cover normalization, trigger sides, deadzones, simultaneous remapped
buttons, D-pad opposites, profile validation, hardware filtering, failure cleanup,
Steam pause, SYN_DROPPED recovery, pad click-drag, gyro activation/timing/stale
output, and rumble effect transactions using simulated devices. Physical USB,
Bluetooth, puck, game compatibility, latency, GUI rendering, and the Arch package
installation still need to be checked on the target machine.

Suggested hardware acceptance checks: start without Steam; verify one virtual pad
per physical controller; check every input in a gamepad tester; disconnect while
holding a button; reconnect; start/exit Steam; stop the bridge and verify that the
virtual pad disappears and the physical controller is released. Also test gyro
activation and orientation, both pad modes, game-triggered rumble, and disconnect
while rumble is playing. Check both controller slots if using a multi-controller puck.

The local PKGBUILD packages the source next to it and works from this checkout
or the source archive. It is not intended for submission to the AUR as-is.

Repository: https://github.com/SuperStellek/SteamBridge

## Sources

- Inspiration: https://github.com/ddeverill/SteamlessController (Windows/ViGEmBus).
- Kernel interface and axis mapping: https://github.com/torvalds/linux/blob/master/drivers/hid/hid-steam.c
- Linux event ABI: https://github.com/torvalds/linux/blob/master/include/uapi/linux/input-event-codes.h
- evdev API: https://python-evdev.readthedocs.io/en/latest/tutorial.html
- Older-kernel raw-HID alternative for research: https://github.com/benashby/steam-puck-bridge

These are external projects; no source from them is bundled. Interface facts were
checked on 2026-10-30. The older bridge README's kernel-support table predates
the current upstream driver and should not be treated as current kernel guidance.

## Remove

```sh
systemctl --user disable --now steambridge.service
sudo pacman -Rns steambridge
sudo udevadm control --reload-rules
```

If the service was never enabled, its stop command is unnecessary. Saved profiles
remain wherever you chose to save them.
