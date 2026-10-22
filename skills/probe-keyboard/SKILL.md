---
name: probe-keyboard
description: Probe keyboards on Ubuntu - list the keycodes each keyboard and button device declares, predict which have a desktop keysym, and listen to live key presses to learn exactly what a physical key emits (evdev name, code, scancode, keysym) and to confirm it physically exists. Use for "what does this key send", "find the keycode of my Fn/vendor/macro key", "which keys does my keyboard actually have", "detect key codes", or before binding a key that has not been pressed yet.
---

# Probe keyboards

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
```

## Declared keys

```bash
python3 "$HKB/probe_keys.py" --save               # every real keyboard / button device
python3 "$HKB/probe_keys.py" --device event4      # full key list of one device
```

Declared keys come from the kernel's capability bitmap. **They are a superset
of the physical keys**: the built-in AT keyboard driver declares about 150,
including F13-F24, whatever the chassis has. Never tell the user a key exists
because it is declared.

## Listen: the only proof a key exists

Needs the user at the keyboard. Tell them which keys to press, then:

```bash
python3 "$HKB/probe_keys.py" --listen --seconds 30 --save
```

Each press prints device, evdev name and code, the scancode (needed for udev
hwdb remaps) and the default keysym. `--save` records the pressed keys as
*physically confirmed* in `keys.json`; later suggestions rank confirmed keys
first. The listener reads `/dev/input` without grabbing, so it cannot swallow
input.

When running it from a non-interactive shell, start it in the background, tell
the user to press keys now, and read the output when it finishes.

What to look for:

- **Fn-layer and vendor keys** (star, phone, settings, keyboard icons) arrive on
  a separate platform device and often as `KEY_PROG1..4`, `KEY_FAVORITES`,
  `KEY_KEYBOARD`, `KEY_PICKUP_PHONE`, `KEY_NOTIFICATION_CENTER`.
- **"no default keysym"** means no desktop shortcut system and no application
  can see the key. Only an interceptor (input-remapper, keyd) can use it.
- **A key that prints nothing** is handled below evdev (firmware Fn keys,
  brightness on some models) or is grabbed by another program
  (input-remapper re-emits on its own virtual device - listen there too:
  `--device` with the "input-remapper keyboard" node).
- **Two keys that print the same name** cannot be told apart by anything above
  the kernel; a hwdb scancode remap is the only way to separate them.

## Interpreting codes

`references/routes.md` § Keys and keysyms lists the default keysyms of the
usual spare keys, including the traps (F13 and KEY_CONFIG share XF86Tools;
F19/F24 have none; F20-F23 are bound to mic mute and touchpad by default).
