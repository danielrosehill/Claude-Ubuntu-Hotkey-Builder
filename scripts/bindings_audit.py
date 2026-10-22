#!/usr/bin/env python3
"""Collect every existing claim on a key, from every layer that can claim one.

Sources, bottom of the stack first:
  hwdb       /etc/udev/hwdb.d/*.hwdb KEYBOARD_KEY_<scancode>=<key> kernel remaps
  keyd       /etc/keyd/*.conf
  remapper   input-remapper presets (~/.config/input-remapper-2/presets), autoload flags
  kanata     ~/.config/kanata/*.kbd (listed, not parsed)
  kde        ~/.config/kglobalshortcutsrc active bindings
  gnome      gsettings keybinding schemas + custom-keybindings
  x11        ~/.xbindkeysrc, ~/.config/sxhkd/sxhkdrc
  manual     claims.json in the reference store: reservations no config file reveals
             (an app's own hotkey, a key you keep for later, a physically dead key)

Each claim is normalised to {source, key, evdev, single_key, action}. `evdev` is
the KEY_* name when the binding can be resolved to one physical key.

  bindings_audit.py [--json] [--save]
  bindings_audit.py --key KEY_F9        only claims touching that key
  bindings_audit.py --reserve KEY_F9 "macropad leader key"   add a manual claim
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import emit, have, host_dir, keynames, now, run, save_json  # noqa: E402

# Qt / KDE and xkb keysym names -> evdev names where they differ from the obvious.
NAME_TO_EVDEV = {
    "print": "KEY_SYSRQ", "sysreq": "KEY_SYSRQ", "menu": "KEY_COMPOSE", "scrolllock": "KEY_SCROLLLOCK",
    "scroll_lock": "KEY_SCROLLLOCK", "pause": "KEY_PAUSE", "break": "KEY_PAUSE", "ins": "KEY_INSERT",
    "insert": "KEY_INSERT", "del": "KEY_DELETE", "delete": "KEY_DELETE", "pgup": "KEY_PAGEUP",
    "pgdown": "KEY_PAGEDOWN", "prior": "KEY_PAGEUP", "next": "KEY_PAGEDOWN", "return": "KEY_ENTER",
    "esc": "KEY_ESC", "escape": "KEY_ESC", "backtab": "KEY_TAB", "space": "KEY_SPACE",
    "tools": "KEY_F13",  # xkb gives F13 the keysym XF86Tools; KDE shows it as "Tools"
    "launch (5)": "KEY_F14", "launch (6)": "KEY_F15", "launch (7)": "KEY_F16", "launch (8)": "KEY_F17",
    "launch (9)": "KEY_F18", "micmute": "KEY_F20", "microphone mute": "KEY_MICMUTE",
    "audiomicmute": "KEY_F20", "touchpad toggle": "KEY_F21", "touchpadtoggle": "KEY_F21",
    "volume down": "KEY_VOLUMEDOWN", "volume up": "KEY_VOLUMEUP", "volume mute": "KEY_MUTE",
    "audiolowervolume": "KEY_VOLUMEDOWN", "audioraisevolume": "KEY_VOLUMEUP", "audiomute": "KEY_MUTE",
    "media play": "KEY_PLAYPAUSE", "audioplay": "KEY_PLAYPAUSE", "media pause": "KEY_PAUSECD",
    "media next": "KEY_NEXTSONG", "audionext": "KEY_NEXTSONG", "media previous": "KEY_PREVIOUSSONG",
    "audioprev": "KEY_PREVIOUSSONG", "media stop": "KEY_STOPCD", "audiostop": "KEY_STOPCD",
    "monitor brightness up": "KEY_BRIGHTNESSUP", "monbrightnessup": "KEY_BRIGHTNESSUP",
    "monitor brightness down": "KEY_BRIGHTNESSDOWN", "monbrightnessdown": "KEY_BRIGHTNESSDOWN",
    "keyboard brightness up": "KEY_KBDILLUMUP", "keyboard brightness down": "KEY_KBDILLUMDOWN",
    "keyboard light on/off": "KEY_KBDILLUMTOGGLE", "favorites": "KEY_FAVORITES", "phone": "KEY_PHONE",
    "battery": "KEY_BATTERY", "screensaver": "KEY_SCREENSAVER", "sleep": "KEY_SLEEP",
    "hibernate": "KEY_SUSPEND", "power off": "KEY_POWER", "power down": "KEY_POWER",
    "calculator": "KEY_CALC", "mail": "KEY_MAIL", "search": "KEY_SEARCH", "explorer": "KEY_FILE",
    "home page": "KEY_HOMEPAGE", "wakeup": "KEY_WAKEUP", "display": "KEY_SWITCHVIDEOMODE",
    "launch (c)": "KEY_SELECTIVE_SCREENSHOT", "meta": "KEY_LEFTMETA", "super": "KEY_LEFTMETA",
}
MODIFIERS = {"ctrl", "control", "alt", "shift", "meta", "super", "hyper", "primary", "altgr", "mod4", "mod1"}


def to_evdev(token):
    """Resolve one key token (no modifiers) to an evdev KEY_* name, or None."""
    t = token.strip()
    if not t:
        return None
    low = t.lower().replace("xf86", "")
    if low in NAME_TO_EVDEV:
        return NAME_TO_EVDEV[low]
    if low.startswith("num+") and len(low) > 4:  # Qt keypad modifier
        kp = {"+": "KPPLUS", "-": "KPMINUS", "*": "KPASTERISK", "/": "KPSLASH", "enter": "KPENTER",
              ".": "KPDOT"}.get(low[4:], low[4:].upper())
        return "KEY_KP" + kp if not kp.startswith("KP") else "KEY_" + kp
    cand = "KEY_" + re.sub(r"[^A-Za-z0-9]", "", t).upper()
    names = set(keynames().values())
    if cand in names:
        return cand
    if len(t) == 1 and t.isalnum():
        return "KEY_" + t.upper()
    return None


def split_combo(combo):
    """'Meta+Ctrl+A' -> (['meta','ctrl'], 'A'); handles 'Num++' and 'Ctrl++'."""
    combo = combo.strip()
    if combo.endswith("++"):
        head, key = combo[:-2], "+"
        parts = [p for p in head.split("+") if p]
        if parts and parts[-1].lower() == "num":
            return parts[:-1], "Num++"
        return parts, key
    parts = combo.split("+")
    mods = [p for p in parts[:-1] if p]
    key = parts[-1]
    if mods and mods[-1].lower() == "num":
        mods, key = mods[:-1], "Num+" + key
    return mods, key


def claim(source, key_str, action, evdev=None, single=None, extra=None):
    c = {"source": source, "key": key_str, "action": action}
    if evdev is None or single is None:
        mods, key = split_combo(key_str)
        real_mods = [m for m in mods if m.lower() in MODIFIERS]
        c["single_key"] = not real_mods
        c["modifiers"] = real_mods
        c["evdev"] = to_evdev(key)
    else:
        c["evdev"], c["single_key"], c["modifiers"] = evdev, single, []
    if extra:
        c.update(extra)
    return c


# ------------------------------------------------------------------ sources

def kde():
    out = []
    path = os.path.expanduser("~/.config/kglobalshortcutsrc")
    if not os.path.exists(path):
        return out
    group = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("["):
            group = line.strip("[]").replace("][", " / ")
            continue
        if "=" not in line or line.startswith("_k_friendly_name"):
            continue
        name, _, val = line.partition("=")
        active = val.split(",")[0]
        if not active or active == "none":
            continue
        # kglobalshortcutsrc separates alternatives with a literal backslash-t
        for combo in active.replace("\\t", "\t").split("\t"):
            if combo and combo != "none":
                out.append(claim("kde", combo, "%s: %s" % (group, name)))
    return out


def gnome():
    out = []
    if not have("gsettings"):
        return out
    schemas = ["org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings",
               "org.gnome.mutter.keybindings", "org.gnome.mutter.wayland.keybindings",
               "org.gnome.settings-daemon.plugins.media-keys"]
    for schema in schemas:
        rc, text = run(["gsettings", "list-recursively", schema])
        if rc != 0:
            continue
        for line in text.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            for accel in re.findall(r"'([^']+)'", parts[2]):
                if accel.startswith("/") or not accel:
                    continue
                out.append(claim("gnome", gnome_to_combo(accel), "%s %s" % (schema, parts[1])))
    rc, text = run(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"])
    for path in re.findall(r"'([^']+)'", text if rc == 0 else ""):
        s = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:" + path
        b = run(["gsettings", "get", s, "binding"])[1].strip().strip("'")
        n = run(["gsettings", "get", s, "name"])[1].strip().strip("'")
        c = run(["gsettings", "get", s, "command"])[1].strip().strip("'")
        if b:
            out.append(claim("gnome", gnome_to_combo(b), "custom: %s -> %s" % (n, c), extra={"path": path}))
    return out


def gnome_to_combo(accel):
    mods = re.findall(r"<([^>]+)>", accel)
    key = re.sub(r"<[^>]+>", "", accel)
    return "+".join([m.capitalize() for m in mods] + [key])


def input_remapper():
    out = []
    base = os.path.expanduser("~/.config/input-remapper-2")
    try:
        autoload = json.load(open(os.path.join(base, "config.json"))).get("autoload", {})
    except (OSError, ValueError):
        autoload = {}
    names = keynames()
    for preset in glob.glob(os.path.join(base, "presets", "*", "*.json")):
        device = os.path.basename(os.path.dirname(preset))
        pname = os.path.splitext(os.path.basename(preset))[0]
        try:
            mappings = json.load(open(preset))
        except (OSError, ValueError):
            continue
        active = autoload.get(device) == pname
        for m in mappings:
            combo = m.get("input_combination") or []
            keys = [names.get(e.get("code"), "code %s" % e.get("code")) for e in combo if e.get("type") == 1]
            if not keys:
                continue
            out.append(claim("input-remapper", "+".join(keys), "-> %s" % m.get("output_symbol"),
                             evdev=keys[-1], single=len(keys) == 1,
                             extra={"device": device, "preset": pname, "autoloaded": active,
                                    "effective": active}))
    return out


def keyd():
    out = []
    for conf in glob.glob("/etc/keyd/*.conf"):
        section = None
        for line in open(conf, errors="replace"):
            line = line.split("#", 1)[0].strip()
            if line.startswith("["):
                section = line.strip("[]")
                continue
            if "=" in line and section not in ("ids", None):
                k, v = [x.strip() for x in line.split("=", 1)]
                ev = to_evdev(k)
                out.append(claim("keyd", k, "[%s] -> %s" % (section, v), evdev=ev,
                                 single=section == "main", extra={"file": conf}))
    return out


def hwdb():
    out = []
    for f in sorted(glob.glob("/etc/udev/hwdb.d/*.hwdb")):
        match = None
        for line in open(f, errors="replace"):
            s = line.strip()
            if s.startswith("evdev:") or s.startswith("keyboard:"):
                match = s
            m = re.match(r"KEYBOARD_KEY_([0-9a-fA-F]+)=(\S+)", s)
            if m:
                target = "KEY_" + m.group(2).upper()
                out.append(claim("hwdb", "scancode %s" % m.group(1).lower(),
                                 "kernel remap -> %s" % target, evdev=target, single=True,
                                 extra={"file": f, "scancode": m.group(1).lower(), "match": match,
                                        "note": "the original key at this scancode no longer exists; "
                                                "%s is now produced by it" % target}))
    return out


def x11_files():
    out = []
    for f in (os.path.expanduser("~/.xbindkeysrc"), os.path.expanduser("~/.config/sxhkd/sxhkdrc")):
        if os.path.exists(f):
            out.append({"source": "x11", "key": None, "action": "config present: %s (not parsed)" % f,
                        "evdev": None, "single_key": None})
    for f in glob.glob(os.path.expanduser("~/.config/kanata/*.kbd")):
        out.append({"source": "kanata", "key": None, "action": "config present: %s (not parsed)" % f,
                    "evdev": None, "single_key": None})
    return out


def manual():
    path = os.path.join(host_dir(), "claims.json")
    try:
        items = json.load(open(path))
    except (OSError, ValueError):
        return []
    return [dict(c, source="manual") for c in items]


def reserve(key, reason):
    path = os.path.join(host_dir(), "claims.json")
    try:
        items = json.load(open(path))
    except (OSError, ValueError):
        items = []
    items = [c for c in items if c.get("evdev") != key]
    items.append({"key": key, "evdev": key, "single_key": True, "action": reason, "added": now()})
    with open(path, "w") as f:
        json.dump(items, f, indent=2)
        f.write("\n")
    return path


def collect(all_desktops=False):
    """Desktop shortcut sources are read only for the running desktop: GNOME's
    schemas are installed on most Ubuntu flavours and would otherwise report
    bindings that nothing is listening for."""
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    sources = [hwdb, keyd, input_remapper, x11_files, manual]
    if all_desktops or "KDE" in desk:
        sources.append(kde)
    if all_desktops or "GNOME" in desk or "UNITY" in desk:
        sources.append(gnome)
    claims = []
    for fn in sources:
        try:
            claims.extend(fn())
        except Exception as e:  # one broken source must not hide the others
            claims.append({"source": fn.__name__, "key": None, "action": "ERROR reading: %s" % e,
                           "evdev": None, "single_key": None})
    return claims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--all-desktops", action="store_true",
                    help="also read KDE/GNOME shortcut config for desktops that are not running")
    ap.add_argument("--key", help="show only claims on this evdev key, e.g. KEY_F9")
    ap.add_argument("--reserve", nargs=2, metavar=("KEY", "REASON"),
                    help="record a manual claim in claims.json")
    args = ap.parse_args()

    if args.reserve:
        k = args.reserve[0].upper()
        k = k if k.startswith("KEY_") else "KEY_" + k
        print("reserved %s in %s" % (k, reserve(k, args.reserve[1])))
        return

    claims = collect(args.all_desktops)
    if args.key:
        k = args.key.upper()
        k = k if k.startswith("KEY_") else "KEY_" + k
        claims = [c for c in claims if c.get("evdev") == k]
    report = {"scanned_at": now(), "claims": claims,
              "single_key_claims": sorted({c["evdev"] for c in claims if c.get("single_key") and c.get("evdev")})}
    if args.save and not args.key:
        report["saved_to"] = save_json("bindings.json", report)
    if emit(report, args.json):
        return
    for c in claims:
        flag = "1-key" if c.get("single_key") else "combo" if c.get("single_key") is False else "  -  "
        print("  %-15s %-5s %-28s %-22s %s" % (c["source"], flag, (c.get("key") or "")[:28],
                                               c.get("evdev") or "", c["action"]))
    print("\n%d claims; %d distinct single keys taken" % (len(claims), len(report["single_key_claims"])))
    if report.get("saved_to"):
        print("Saved " + report["saved_to"])


if __name__ == "__main__":
    main()
