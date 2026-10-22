# Binding routes on Ubuntu

How a physical key can be made to do something, layer by layer, and which layer
to use when. Everything marked **verified** was observed on Ubuntu 26.04.1,
KDE Plasma 6.6.6 / KWin 6.6.6 on Wayland, input-remapper 2.2.0, ydotool 1.0.4,
on 2026-10-22, unless another date is given. Everything else is marked inferred.

## The stack

```
physical key
  -> kernel driver (scancode -> evdev keycode)      udev hwdb rewrites here (KEYBOARD_KEY_<scancode>=<key>)
  -> /dev/input/eventN                              input-remapper, keyd, kanata, evdev readers act here
  -> compositor (keycode+8 -> xkb keysym)           KDE / GNOME global shortcuts act here
  -> focused application                            app-level shortcuts, terminal escape sequences
```

A binding at a lower layer hides the key from every layer above it.

## Choosing a route

| Want | Desktop | Route | Script |
| --- | --- | --- | --- |
| key runs a command / types text | KDE | desktop shortcut via kglobalaccel D-Bus, command = `hkb-type` | `bind_kde.py --bind` |
| key runs a command / types text | GNOME | gsettings custom keybinding | `bind_gnome.py --bind` |
| key types text, single Latin layout | any | input-remapper text macro | `bind_input_remapper.py --text` |
| key types text, several layouts | KDE/GNOME | **two-stage**: input-remapper maps key -> spare F14-F18, desktop binds that to `hkb-type` (which pins the layout) | both |
| keypad key runs anything on KDE | KDE | two-stage (KWin does not fire keypad shortcuts) | both |
| key with no keysym (KEY_MACRO*, phone keys, many vendor keys) | any | interceptor, or two-stage | `bind_input_remapper.py` |
| key becomes another key everywhere, even on the console | any | udev hwdb (needs sudo) | manual, see below |

## Facts that decide routes

**KWin does not re-read `kglobalshortcutsrc`** (verified; also recorded 2026-08-10).
Plasma 6.6 has no separate kglobalacceld: KWin serves `org.kde.kglobalaccel`.
Hand-editing the file does nothing until the next login. Register over D-Bus:
`doRegister(['<file>.desktop','_launch','Name','Name'])` then
`setForeignShortcut(<same id>, [<Qt key int>])`. The binding is persisted under
`[services][<file>.desktop]` by kglobalaccel itself.

**The launcher must be in the KService cache before registration** (verified).
A `.desktop` written and registered in the same instant was stored correctly
under `[services]`, reported by `getGlobalShortcutsByKey`, and never launched,
even via `invokeShortcut`. After `kbuildsycoca6` and re-registering, the same
component launched. `bind_kde.py` runs `kbuildsycoca6` between the two.

**Synthetic key presses do not prove anything on KDE** (verified, cause not
established). Keys sent with `ydotool key` reached evdev (seen on the ydotoold
virtual device) but fired neither a launcher bound to Pause or F9 nor
powerdevil's own keyboard-light shortcut. Verify with a physical press:
`bind_kde.py --verify KEY --seconds 20`.

**No hyphen in the launcher's file name** (inferred, chosen defensively).
kglobalaccel derives a D-Bus object path from the component name
(`hkb_type_claude.desktop` -> `/component/hkb_type_claude_desktop`); hyphens are
not valid in object path elements. The scripts use `hkb_<slug>.desktop`.

**KWin does not fire global shortcuts on keypad keys** (verified 2026-08-10 on
the same KWin version: `Num++` registered cleanly, encoding confirmed by
kglobalaccel's own write-back, never fired). Use two-stage for keypad keys.

**wtype does not work on KWin or Mutter** (verified for KWin:
`wayland-info` lists no `zwp_virtual_keyboard_manager_v1`). `ydotool` via
`/dev/uinput` is the injector that works; `env_check.py` tests the protocol.

**ydotool is layout-sensitive.** It emits US-layout keycodes, which the
compositor maps through the *active* layout. With Hebrew (or any non-Latin
layout) active, `claude` comes out in Hebrew letters. On KDE, `hkb-type` pins
the first Latin layout over D-Bus (`org.kde.keyboard /Layouts setLayout N`) for
the duration of the injection and restores the previous one. Even with a Latin
layout, symbols that sit elsewhere on non-US layouts (`"` and `@` on a UK
layout) come out swapped: ydotool assumes US positions.

**ydotool escapes.** `ydotool type` interprets backslash escapes in its
arguments; `hkb-type` passes text on stdin (`-f -`), where escapes are off.

**Ubuntu ships a user unit for ydotoold** (verified): `/usr/lib/systemd/user/ydotool.service`.
`systemctl --user enable --now ydotool` gives a user-owned socket at
`$XDG_RUNTIME_DIR/.ydotool_socket`; no root, no udev rule, provided the user is
in the `input` group and `/dev/uinput` is group `input` writable.

## Keys and keysyms

The desktop sees a keysym, not a keycode. Default (`evdev` ruleset,
xkeyboard-config on Ubuntu 26.04) keysyms of the usual spare keys:

| evdev key | code | keysym | Notes |
| --- | --- | --- | --- |
| KEY_F13 | 183 | XF86Tools | KDE shows it as "Tools". **Same keysym as KEY_CONFIG (171)**: a desktop binding on one fires for both |
| KEY_F14..F18 | 184-188 | XF86Launch5..9 | KDE shows "Launch (5)".."Launch (9)". Best two-stage targets |
| KEY_F19, KEY_F24 | 189, 194 | none | invisible to the desktop |
| KEY_F20 | 190 | XF86AudioMicMute | bound to mic mute by default |
| KEY_F21 | 191 | XF86TouchpadToggle | bound by default |
| KEY_F22, KEY_F23 | 192, 193 | XF86TouchpadOn / Off | GNOME binds both |
| KEY_PROG1..4 | 148, 149, 202, 203 | XF86Launch1..4 | the ThinkPad hotkey driver declares PROG1, 3, 4 |
| KEY_FAVORITES | 364 | XF86Favorites | code above 247 but visible on Wayland |
| KEY_MACRO1.. | 656.. | XF86Macro1.. | keysym exists, but Qt has no key for it: not bindable in KDE |
| KEY_PAUSE / KEY_SCROLLLOCK / KEY_COMPOSE | 119 / 70 / 127 | Pause / Scroll_Lock / Menu | common free keys |

`hkb_common.xkb_keysym()` predicts these from `/usr/share/X11/xkb`; the
physical verify is the authority.

**Declared is not physical.** The AT keyboard driver declares ~150 keys
including F13-F24 regardless of what the chassis has. Confirm with
`probe_keys.py --listen --save`.

## input-remapper notes (2.2.0)

- Presets: `~/.config/input-remapper-2/presets/<device name>/<preset>.json`,
  autoload map in `~/.config/input-remapper-2/config.json`. One active preset
  per device.
- `input-remapper-control --command start --device <name> --preset <preset>`
  applies without the GUI; `--list-devices` gives the exact names.
- The device is grabbed and re-emitted through "input-remapper keyboard"; other
  evdev readers (dictation tools, keyd) must then read that virtual device.
- Macro functions: `key`, `key_down`, `key_up`, `modify`, `repeat`, `wait`,
  `hold`, `hold_keys`, `if_tap`, `if_single`, `mod_tap`, `parallel`, `set`,
  `if_eq`, `add`, `event`, `mouse`, `wheel`. There is **no `text()`**; text is a
  chain of `key()` / `modify(KEY_LEFTSHIFT, key())`. Presets cannot run commands.

## udev hwdb (kernel remap, needs sudo)

```
# /etc/udev/hwdb.d/90-hotkey.hwdb
evdev:atkbd:dmi:bvn*:bvr*:bd*:br*:efr*:svn<VENDOR>:pn<PRODUCT>:*
 KEYBOARD_KEY_<scancode>=<keyname>
```

Scancode from `probe_keys.py --listen` (MSC_SCAN). Apply:
`sudo systemd-hwdb update && sudo udevadm trigger --subsystem-match=input --action=change`.
Use it to turn a key into another *key*; it cannot type text or run commands.
