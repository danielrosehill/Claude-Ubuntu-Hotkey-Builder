---
description: Scan and document all available keycodes on the system
---

# Keycode Scanner

Scan the Linux system for all available keycodes and document them.

## Step 1: Detect Display Server

Run: `echo $XDG_SESSION_TYPE` or check if Wayland or X11 is in use.

## Step 2: Gather Keycode Data

### For X11 systems:
1. Run `xmodmap -pke` to get the full keycode-to-keysym mapping
2. Run `setxkbmap -print -verbose 10` to get the current XKB layout configuration
3. Read `/usr/share/X11/xkb/keycodes/evdev` for the full evdev keycode definitions

### For Wayland systems:
1. Run `xmodmap -pke` (may still work via XWayland)
2. Read `/usr/share/X11/xkb/keycodes/evdev` for reference
3. Note that `libinput debug-events` or `evtest` can be used for interactive testing

### For both:
1. Check `cat /proc/bus/input/devices` to list all input devices
2. Run `lsusb` and `xinput list` (if X11) to identify connected keyboards

## Step 3: Identify the Keyboard Profile

Resolve the plugin's data directory as `$CLAUDE_USER_DATA/keyboard-scanner/` if `CLAUDE_USER_DATA` is set; otherwise `$XDG_DATA_HOME/claude-plugins/keyboard-scanner/` if `XDG_DATA_HOME` is set; otherwise `~/.local/share/claude-plugins/keyboard-scanner/`. Referred to below as `$DATA`.

Check `$DATA/keyboards/` for existing profiles. If a profile exists, associate this scan with it. If not, suggest the user runs `/keyboard-intake` first.

## Step 4: Organize and Save

Create `$DATA/keycodes/{name-slug}-keycodes.md` with:

```markdown
# Keycode Map: {Keyboard Name}

## System Info
- **Display Server**: X11 / Wayland
- **XKB Layout**: ...
- **XKB Variant**: ...
- **XKB Model**: ...
- **Scan Date**: {date}

## Input Devices Detected
(list from /proc/bus/input/devices relevant to keyboards)

## Full Keycode Map
| Keycode | Keysym(s) | Description |
|---------|-----------|-------------|
| 9       | Escape    | Escape key  |
| 10      | 1, exclam | 1 / !       |
| ...     | ...       | ...         |

## Special/Unusual Keys
List any keycodes that map to uncommon functions:
- Insert, Scroll Lock, Pause/Break
- Function keys beyond F12
- Multimedia keys
- Vendor-specific keys (ThinkPad buttons, etc.)

## Unassigned Keycodes
List any keycodes with no current keysym assignment (candidates for remapping).
```

Also save a full keymap reference to `$DATA/keymaps/{name-slug}-keymap.md`.

## Step 5: Summary

Tell the user:
- How many keycodes were found
- How many have keysym assignments
- How many are unassigned (remap candidates)
- Any notable special keys detected
- Suggest running `/suggest-remaps` next
