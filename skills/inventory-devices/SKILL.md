---
name: inventory-devices
description: Inventory input hardware on Ubuntu - run lsusb and map every /dev/input/event* device to its vendor:product ID, bus (USB, Bluetooth, built-in i8042, virtual uinput), device class (keyboard, buttons, pointer, virtual) and stable /dev/input/by-id path, then record it in the per-machine reference and diff against the last scan. Use when the user asks "what keyboards / input devices do I have", "get the USB IDs of my macropad / foot pedal / keyboard", "which device is this", or before binding a key on a specific device.
---

# Inventory input devices

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
python3 "$HKB/usb_inventory.py" --save
```

The table lists USB devices (root hubs hidden) and every evdev input device:

| Column | Meaning |
| --- | --- |
| node | `eventN` - **not stable**, changes with plug order. Never key a binding on it |
| vid:pid | vendor:product - stable; what input-remapper presets and keyd `[ids]` match on |
| class | `keyboard` (has letter keys), `buttons` (keys but no letters: vendor hotkeys, pedals, macropads), `pointer`, `virtual`, `other` |
| bus | `usb`, `bluetooth`, `i8042 (built-in)` = laptop keyboard, `virtual (uinput)` = created by software |
| keys | how many keys the driver *declares* - a superset of the physical keys |

## Reading it

- **Virtual devices are other software already in the input path**: ydotoold,
  input-remapper's output keyboard, Espanso, dictation tools, remap daemons.
  Each is a sign of an existing interceptor or injector; mention them, and note
  that if input-remapper grabs a keyboard, other evdev readers must read
  "input-remapper keyboard" instead.
- **Classification by sysfs path**: uinput devices often claim bus `usb` with
  made-up IDs. The script trusts `/devices/virtual/` in the sysfs path instead.
- **One physical product can appear as several devices** (a keyboard plus a
  "Consumer Control" and "System Control" node for media keys). Media keys
  usually arrive on the extra node - bind on that one.
- **The laptop's vendor keys** (ThinkPad, Dell, HP hotkeys) are usually a
  separate platform device (`ThinkPad Extra Buttons`, `Dell WMI hotkeys`).

## Diff

With `--save`, the output ends with what was added or removed since the last
saved scan - the quickest way to identify a newly plugged device: run it,
plug the device in, run it again.

Saved to `devices.json` in the per-machine reference; `reference.py render`
puts the table in the reference README.
