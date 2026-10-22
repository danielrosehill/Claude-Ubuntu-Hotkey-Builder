# Hotkey Builder (Ubuntu)

Claude skills for finding free keys on an Ubuntu machine and turning them into
shortcuts that actually work: a single key that types `claude` and presses
Enter, a key that runs a command, a spare key remapped to another.

The hard part of a laptop hotkey is not the binding, it is everything around
it - which keys physically exist, which are already claimed (and by which of
five layers), which injector works on this compositor, and which route the
desktop will actually honour. This plugin does that legwork with scripts and
keeps what it learns in a per-machine reference so the next scan starts from it.

## Skills

| Skill | Does |
| --- | --- |
| `check-environment` | X11/Wayland, KDE/GNOME, injectors (ydotool, wtype, xdotool), interceptors (input-remapper, keyd, kanata), whether their services really run, input-group and uinput access, layouts; installs what is missing; recommends an injector and interceptor |
| `inventory-devices` | `lsusb` plus every evdev device with vendor:product, bus, class, stable path; diffs against the last scan |
| `probe-keyboard` | keys each device declares, predicted keysyms, and a live listener that records what a key really emits (code, scancode) and confirms it exists |
| `audit-bindings` | every claim on a key: udev hwdb, keyd, input-remapper presets, KDE (file and live D-Bus), GNOME, xbindkeys/sxhkd, plus manual reservations |
| `suggest-shortcut` | ranks free single keys for a purpose (text / command / key) with the route each needs and its caveats |
| `create-shortcut` | the whole flow: request -> environment -> candidates -> physical confirm -> bind by route -> verify by real press -> log with undo |

## Routes

| Route | When |
| --- | --- |
| KDE global shortcut over kglobalaccel D-Bus | key has a keysym and is not on the keypad; applies live, no logout |
| GNOME custom keybinding via gsettings | GNOME; applies live |
| input-remapper macro | any key, any desktop; text only with a single Latin layout |
| two-stage | input-remapper maps the key to a spare F14-F18, the desktop binds that - for keypad keys on KDE, keys with no keysym, and text on multi-layout machines |

Text is typed by `hkb-type` (`scripts/inject_text.py`): wtype where the
compositor supports it, otherwise ydotool with the Latin layout pinned for the
duration on KDE, otherwise xdotool on X11.

[`references/routes.md`](references/routes.md) has the facts behind each choice,
with what was verified and when - including several that cost hours to find
(KWin ignores a launcher registered before the KService cache knows it; KWin
does not fire shortcuts for keypad keys; F13 and KEY_CONFIG share a keysym;
synthetic key presses do not trigger KWin shortcuts).

## Scripts

Standard-library Python 3, usable on their own. Each takes `--json`; most take
`--save` to write into the reference.

| Script | Purpose |
| --- | --- |
| `env_check.py` | environment report, `--install-cmd` |
| `usb_inventory.py` | lsusb + evdev inventory |
| `probe_keys.py` | declared keys, `--listen` |
| `bindings_audit.py` | all claims, `--key`, `--reserve` |
| `suggest_keys.py` | ranked candidates, `--purpose` |
| `bind_kde.py` | `--check` / `--verify` / `--bind` / `--unbind` / `--list` |
| `bind_gnome.py` | `--bind` / `--unbind` / `--list` |
| `bind_input_remapper.py` | `--text` / `--to-key` / `--macro` / `--unbind` / `--list` |
| `inject_text.py` | install as `~/.local/bin/hkb-type` |
| `reference.py` | `path` / `status` / `log` / `render` |

## Per-machine reference

`<root>/hotkey-builder/<hostname>/` - JSON from each scan, `claims.json` for
reservations no config file reveals (edit by hand), `shortcuts.json` for what
was created with its undo command, and a rendered `README.md`.

`<root>` is `$HKB_DATA_DIR` if set, else `$CLAUDE_USER_DATA/hotkey-builder`,
else the first of `~/.claude-user-data` and `${XDG_DATA_HOME:-~/.local/share}/claude-plugins`
that already exists, else `~/.claude-user-data`. `reference.py path` prints it.

## Requirements

Ubuntu (developed on 26.04 LTS; the scripts only need Python 3, `/proc`, `/sys`
and the tools they report on). Membership of the `input` group for probing and
injection. Each tool is optional; `check-environment` reports and installs.

## Install

```
/plugin marketplace add danielrosehill/Claude-Code-Plugins
/plugin install hotkey-builder@danielrosehill
```

Related: [`keyboard-scanner`](https://github.com/danielrosehill/Claude-Keyboard-Scanner)
profiles keyboards through a questionnaire and suggests remap ideas; this plugin
measures the machine and implements the binding.

## License

MIT
