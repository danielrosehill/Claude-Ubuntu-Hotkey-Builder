#!/usr/bin/env python3
"""Rank free single keys for a new shortcut, with the route each one needs.

Joins three things: the keys real keyboards declare (probe_keys), every claim
already on a key (bindings_audit), and which keys have been physically
confirmed by pressing them (keys.json). Scores each candidate on how unlikely it
is to collide with anything, and says how it can be bound:

  desktop      a KDE / GNOME global shortcut runs a command (needs code <= 247;
               KWin ignores keypad keys)
  interceptor  input-remapper / keyd catch it below the compositor (any key)
  two-stage    interceptor remaps it to a spare F13-F24 key, desktop binds that
               (for keypad and >247 keys when a desktop command is wanted)

  suggest_keys.py --purpose text  [--top 10] [--json] [--save]
  purpose: text (inject a string), command (run a program), key (remap to another key)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bindings_audit  # noqa: E402
import probe_keys  # noqa: E402
from hkb_common import (device_keys, emit, keycode, keyname, load_json, now, qt_key,  # noqa: E402
                        save_json, xkb_keysym)

# name: (score, why it is a candidate, caveat or None)
CANDIDATES = {
    **{"KEY_F%d" % n: (90, "extended function key; nothing binds it by default", None)
       for n in (13, 14, 15, 16, 17, 18, 19, 24)},
    "KEY_F22": (20, "extended function key", "xkb maps F22 to XF86TouchpadOn"),
    "KEY_F23": (20, "extended function key", "xkb maps F23 to XF86TouchpadOff"),
    "KEY_F20": (20, "extended function key", "xkb maps F20 to XF86AudioMicMute; desktops bind it to mic mute"),
    "KEY_F21": (20, "extended function key", "xkb maps F21 to XF86TouchpadToggle; desktops bind it"),
    "KEY_PROG1": (85, "vendor programmable key", None),
    "KEY_PROG2": (85, "vendor programmable key", None),
    "KEY_PROG3": (85, "vendor programmable key", None),
    "KEY_PROG4": (85, "vendor programmable key", None),
    "KEY_SCROLLLOCK": (85, "Scroll Lock does nothing on a modern desktop", None),
    "KEY_PAUSE": (85, "Pause/Break does nothing on a modern desktop", None),
    "KEY_COMPOSE": (75, "Menu/context key; rarely used", "loses the right-click-menu key"),
    "KEY_INSERT": (75, "Insert mostly toggles overtype by accident", "loses Shift+Insert paste in terminals"),
    "KEY_KPSLASH": (70, "numpad operator, almost never used", "keypad: KWin does not fire global shortcuts"),
    "KEY_KPASTERISK": (70, "numpad operator, almost never used", "keypad: KWin does not fire global shortcuts"),
    "KEY_KPMINUS": (68, "numpad operator", "keypad: KWin does not fire global shortcuts"),
    "KEY_KPPLUS": (68, "numpad operator", "keypad: KWin does not fire global shortcuts"),
    "KEY_KPENTER": (60, "duplicates main Enter", "keypad: KWin does not fire global shortcuts; "
                    "some apps treat it as Enter"),
    "KEY_F9": (60, "the least-used classic F-key in applications", "some apps: F9 = compile/sidebar"),
    "KEY_F8": (50, "classic F-key", "app-level uses exist (debuggers)"),
    "KEY_F7": (45, "classic F-key", "F7 = caret browsing in Firefox/Chrome"),
    "KEY_F10": (45, "classic F-key", "F10 = open menu bar in many apps"),
    "KEY_F6": (40, "classic F-key", "F6 = focus address bar in browsers"),
    "KEY_F2": (40, "classic F-key", "F2 = rename in file managers/spreadsheets"),
    "KEY_F3": (35, "classic F-key", "F3 = find next"),
    "KEY_F4": (35, "classic F-key", "Alt+F4 closes windows; plain F4 used by some apps"),
    "KEY_F1": (30, "classic F-key", "F1 = help everywhere"),
    "KEY_F12": (25, "classic F-key", "F12 = browser devtools"),
    "KEY_F5": (20, "classic F-key", "F5 = refresh"),
    "KEY_F11": (20, "classic F-key", "F11 = fullscreen"),
    "KEY_RIGHTCTRL": (40, "right Ctrl", "only if you never use it as a modifier"),
    "KEY_CAPSLOCK": (40, "Caps Lock", "popular remap target; disruptive if you ever use caps"),
    "KEY_RIGHTALT": (15, "right Alt", "is AltGr on many layouts (accents, third-level symbols)"),
    "KEY_NUMLOCK": (30, "NumLock", "breaks numpad digits if you rely on them"),
}
VENDOR = ["KEY_FAVORITES", "KEY_KEYBOARD", "KEY_NOTIFICATION_CENTER", "KEY_PICKUP_PHONE", "KEY_HANGUP_PHONE",
          "KEY_LINK_PHONE", "KEY_SELECTIVE_SCREENSHOT", "KEY_VENDOR", "KEY_FULL_SCREEN", "KEY_MESSENGER",
          "KEY_CHAT", "KEY_PHONE", "KEY_CONFIG", "KEY_VOICECOMMAND", "KEY_ASSISTANT", "KEY_MACRO1",
          "KEY_MACRO2", "KEY_MACRO3", "KEY_MACRO4"]
for v in VENDOR:
    CANDIDATES.setdefault(v, (65, "vendor/special key", "only if you do not want its printed function"))

EXTENDED_F = {"KEY_F%d" % n for n in range(13, 25)}
KEYPAD = {"KEY_KPSLASH", "KEY_KPASTERISK", "KEY_KPMINUS", "KEY_KPPLUS", "KEY_KPENTER"}


def routes(name, keysym, desktop):
    """Which binding routes can work for this key.

    desktop: the compositor must see a keysym, and on KDE kglobalaccel must be
    able to encode it (and KWin ignores keypad keys)."""
    r = []
    if desktop == "kde":
        if qt_key(keysym) and name not in KEYPAD:
            r.append("desktop")
    elif desktop == "gnome" and keysym:
        r.append("desktop")
    r.append("interceptor")
    if "desktop" not in r and desktop in ("kde", "gnome"):
        r.append("two-stage")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--purpose", choices=("text", "command", "key"), default="text")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--include-unconfirmed", action="store_true", default=True)
    args = ap.parse_args()

    deskenv = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    desktop = "kde" if "KDE" in deskenv else "gnome" if ("GNOME" in deskenv or "UNITY" in deskenv) else "other"
    env = load_json("environment.json") or {}
    multi_layout = len(env.get("layouts", [])) > 1

    declared = {}
    for d in probe_keys.real_devices():
        for c in device_keys(d):
            declared.setdefault(keyname(c), []).append("%s (%s)" % (d.get("name"), d["event"]))
    by_keysym = {}
    for n in declared:
        try:
            ks = xkb_keysym(keycode(n))
        except KeyError:
            continue
        if ks:
            by_keysym.setdefault(ks, []).append(n)
    confirmed = set()
    for keys in (load_json("keys.json") or {}).get("confirmed", {}).values():
        confirmed.update(keys)

    claims = bindings_audit.collect()
    single = {}
    combo = {}
    for c in claims:
        ev = c.get("evdev")
        if not ev:
            continue
        if c.get("single_key") and c.get("effective", True):
            single.setdefault(ev, []).append("%s: %s" % (c["source"], c["action"]))
        elif not c.get("single_key"):
            combo.setdefault(ev, []).append(c["key"])
    # keys whose scancode an hwdb rule rewrote no longer exist under their old name;
    # we cannot name the old key without the vendor table, so we surface the scancodes
    hwdb_scancodes = sorted({c["scancode"] for c in claims if c["source"] == "hwdb"})

    ranked, taken, targets = [], [], []
    for name, (score, why, caveat) in CANDIDATES.items():
        if name not in declared:
            continue
        try:
            code = keycode(name)
        except KeyError:
            continue
        keysym = xkb_keysym(code)
        entry = {"key": name, "code": code, "keysym": keysym, "score": score, "why": why, "caveat": caveat,
                 "devices": declared[name], "physically_confirmed": name in confirmed,
                 "routes": routes(name, keysym, desktop)}
        twins = [k for k in by_keysym.get(keysym, []) if k != name] if keysym else []
        if twins:
            entry.setdefault("notes", []).append(
                "shares keysym %s with %s: a desktop binding fires for both" % (keysym, ", ".join(twins)))
        if name in single:
            entry["claimed_by"] = single[name]
            taken.append(entry)
            continue
        if name in combo:
            entry["used_in_combos"] = combo[name][:5]
        if name in EXTENDED_F and not entry["physically_confirmed"]:
            # every AT/USB driver declares F13-F24, almost no keyboard has them;
            # they are worth more as invisible targets for a two-stage remap
            if "desktop" in entry["routes"] and score >= 90 and not entry.get("used_in_combos") and not twins:
                targets.append(name)
            continue
        if not entry["physically_confirmed"]:
            entry["score"] -= 25
        if args.purpose in ("text", "command") and "desktop" not in entry["routes"]:
            entry["score"] -= 10  # needs an interceptor (or two stages) to run anything
        if args.purpose == "text" and multi_layout and "desktop" not in entry["routes"]:
            entry.setdefault("notes", []).append(
                "multiple layouts: an interceptor macro types keycodes through whatever layout is active; "
                "prefer two-stage so inject_text.py can pin the Latin layout")
        ranked.append(entry)
    ranked.sort(key=lambda e: -e["score"])

    report = {"generated_at": now(), "purpose": args.purpose, "desktop": desktop,
              "multiple_layouts": multi_layout, "suggestions": ranked[:args.top],
              "excluded_as_taken": taken, "two_stage_targets": targets, "hwdb_remapped_scancodes": hwdb_scancodes,
              "warning": "declared keys are a superset of the physical keys; confirm with "
                         "probe_keys.py --listen --save before binding"}
    if args.save:
        report["saved_to"] = save_json("suggestions-%s.json" % args.purpose, report)
    if emit(report, args.json):
        return
    print("Free single keys for purpose=%s on %s%s\n" % (args.purpose, desktop,
                                                          " (multiple layouts)" if multi_layout else ""))
    for e in report["suggestions"]:
        print("%3d  %-22s %-9s routes=%-30s %s" % (e["score"], e["key"],
                                                    "pressed" if e["physically_confirmed"] else "declared",
                                                    ",".join(e["routes"]), e["why"]))
        if e.get("caveat"):
            print("       caveat: " + e["caveat"])
        if e.get("used_in_combos"):
            print("       also in combos: " + ", ".join(e["used_in_combos"]))
        for n in e.get("notes", []):
            print("       note: " + n)
    if taken:
        print("\nAlready taken:")
        for e in taken:
            print("  %-22s %s" % (e["key"], "; ".join(e["claimed_by"])))
    if targets:
        print("\nFree two-stage targets (declared, not physical; remap a real key onto one, bind it on the desktop):")
        print("  " + " ".join(targets))
    if hwdb_scancodes:
        print("\nScancodes rewritten by hwdb (their original keys are gone): " + " ".join(hwdb_scancodes))
    print("\n" + report["warning"])
    if report.get("saved_to"):
        print("Saved " + report["saved_to"])


if __name__ == "__main__":
    main()
