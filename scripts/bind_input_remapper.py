#!/usr/bin/env python3
"""Map one physical key on one device with input-remapper (below the compositor).

Works on X11 and Wayland, on any desktop, for any key including keypad keys
and keys with no keysym. input-remapper grabs the whole device and re-emits
everything else through its own virtual keyboard, so the rest of the keyboard
keeps working.

  bind_input_remapper.py --device "AT Translated Set 2 keyboard" --key KEY_KPSLASH --text "claude" --enter
  bind_input_remapper.py --device ... --key KEY_KPSLASH --to-key KEY_F14      (two-stage: remap, bind F14 on the desktop)
  bind_input_remapper.py --device ... --key KEY_KPSLASH --macro "key(KEY_A).wait(50).key(KEY_B)"
  bind_input_remapper.py --device ... --unbind KEY_KPSLASH
  bind_input_remapper.py --list

Options: --preset NAME (default "hotkey-builder"), --no-apply (write files only).

Caveats, all verified against input-remapper 2.2.0:
  - a macro emits keycodes, so typed text follows the ACTIVE xkb layout; with
    several layouts, prefer the two-stage route so hkb-type can pin the layout;
  - only one preset per device is active; this script adds to the device's
    autoloaded preset when one exists rather than replacing it;
  - an input-remapper preset can only emit events, never run a command.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import keycode, keyname  # noqa: E402

BASE = os.path.expanduser("~/.config/input-remapper-2")

# characters reachable on a US layout: char -> (KEY_*, shift)
_US = {}
for c in "abcdefghijklmnopqrstuvwxyz":
    _US[c] = ("KEY_" + c.upper(), False)
    _US[c.upper()] = ("KEY_" + c.upper(), True)
for c, n in zip("1234567890", "1234567890"):
    _US[c] = ("KEY_" + n, False)
for c, k in zip("!@#$%^&*()", "1234567890"):
    _US[c] = ("KEY_" + k, True)
for c, k, s in ((" ", "SPACE", False), ("-", "MINUS", False), ("_", "MINUS", True), ("=", "EQUAL", False),
                ("+", "EQUAL", True), ("[", "LEFTBRACE", False), ("{", "LEFTBRACE", True),
                ("]", "RIGHTBRACE", False), ("}", "RIGHTBRACE", True), (";", "SEMICOLON", False),
                (":", "SEMICOLON", True), ("'", "APOSTROPHE", False), ('"', "APOSTROPHE", True),
                (",", "COMMA", False), ("<", "COMMA", True), (".", "DOT", False), (">", "DOT", True),
                ("/", "SLASH", False), ("?", "SLASH", True), ("`", "GRAVE", False), ("~", "GRAVE", True),
                ("\\", "BACKSLASH", False), ("|", "BACKSLASH", True), ("\t", "TAB", False),
                ("\n", "ENTER", False)):
    _US[c] = ("KEY_" + k, s)


def text_macro(text, enter=False):
    parts = []
    for ch in text:
        if ch not in _US:
            raise SystemExit("cannot type %r through a keycode macro; use the two-stage route with hkb-type" % ch)
        k, shift = _US[ch]
        parts.append("modify(KEY_LEFTSHIFT, key(%s))" % k if shift else "key(%s)" % k)
    if enter:
        parts.append("key(KEY_ENTER)")
    return ".".join(parts)


def device_names():
    p = subprocess.run(["input-remapper-control", "--list-devices"], capture_output=True, text=True)
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]


def config():
    try:
        return json.load(open(os.path.join(BASE, "config.json")))
    except (OSError, ValueError):
        return {"version": "2.2.0", "autoload": {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", help="device name as input-remapper-control --list-devices prints it")
    ap.add_argument("--key")
    ap.add_argument("--preset", default=None)
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--text")
    out.add_argument("--to-key")
    out.add_argument("--macro")
    out.add_argument("--unbind", metavar="KEY")
    ap.add_argument("--enter", action="store_true")
    ap.add_argument("--no-apply", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        cfg = config()
        for f in sorted(glob.glob(os.path.join(BASE, "presets", "*", "*.json"))):
            dev = os.path.basename(os.path.dirname(f))
            pre = os.path.splitext(os.path.basename(f))[0]
            active = cfg.get("autoload", {}).get(dev) == pre
            for m in json.load(open(f)):
                keys = [keyname(e["code"]) for e in m.get("input_combination", []) if e.get("type") == 1]
                print("  %-40s %-22s %-6s %s -> %s" % (dev[:40], pre[:22], "AUTO" if active else "", "+".join(keys),
                                                       m.get("output_symbol")))
        return
    if not args.device:
        ap.error("--device is required")
    names = device_names()
    if names and args.device not in names:
        raise SystemExit("input-remapper does not know %r. Devices: %s" % (args.device, "; ".join(names)))

    cfg = config()
    preset = args.preset or cfg.get("autoload", {}).get(args.device) or "hotkey-builder"
    path = os.path.join(BASE, "presets", args.device, preset + ".json")
    try:
        mappings = json.load(open(path))
    except (OSError, ValueError):
        mappings = []

    target = args.unbind or args.key
    if not target:
        ap.error("--key is required")
    code = keycode(target)
    mappings = [m for m in mappings
                if not any(e.get("type") == 1 and e.get("code") == code for e in m.get("input_combination", []))]
    if not args.unbind:
        if args.text is not None:
            symbol = text_macro(args.text, args.enter)
        elif args.to_key:
            symbol = keyname(keycode(args.to_key))
        elif args.macro:
            symbol = args.macro
        else:
            ap.error("one of --text / --to-key / --macro")
        mappings.append({"input_combination": [{"type": 1, "code": code}],
                         "target_uinput": "keyboard", "output_symbol": symbol, "mapping_type": "key_macro"})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(mappings, f, indent=4)
        f.write("\n")
    cfg.setdefault("autoload", {})[args.device] = preset
    with open(os.path.join(BASE, "config.json"), "w") as f:
        json.dump(cfg, f, indent=4)
        f.write("\n")
    print("%s %s on %r in preset %r (%s)" % ("removed" if args.unbind else "mapped", keyname(code), args.device,
                                             preset, path))
    if not args.unbind:
        print("  -> " + mappings[-1]["output_symbol"])
    if not args.no_apply:
        subprocess.run(["input-remapper-control", "--command", "stop", "--device", args.device],
                       capture_output=True)
        p = subprocess.run(["input-remapper-control", "--command", "start", "--device", args.device,
                            "--preset", preset], capture_output=True, text=True)
        print("  applied: %s" % ("yes" if p.returncode == 0 else "NO - " + (p.stderr or p.stdout).strip()[-300:]))


if __name__ == "__main__":
    main()
