#!/usr/bin/env python3
"""Probe keyboards: what keys each device declares, and what a key really emits.

Declared keys come from the kernel's capability bitmap and are a SUPERSET of
the keys the chassis physically has (the AT driver declares ~150 whatever the
layout). Listening is the only proof a key exists, and it also gives the
scancode, which is what a udev hwdb remap needs.

  probe_keys.py                     declared keys per real keyboard/button device
  probe_keys.py --device event4     one device, full key list
  probe_keys.py --listen [-t 20]    print every key press on every keyboard until timeout
  probe_keys.py --listen --save     ...and record pressed keys as physically confirmed
  probe_keys.py --save              write keys.json (keeps earlier confirmations)

Listening reads /dev/input/event* directly (user must be in the 'input' group),
does not grab devices, and so cannot swallow input.
"""

import argparse
import os
import select
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import (xkb_keysym, classify, device_keys, emit, input_devices,  # noqa: E402
                        keyname, load_json, now, save_json)

EV_KEY, EV_MSC, MSC_SCAN = 0x01, 0x04, 0x04
EVENT = struct.Struct("llHHi")  # timeval (2 longs), type, code, value


def real_devices(only=None):
    out = []
    for d in input_devices():
        if not d.get("event"):
            continue
        if only and d["event"] != only:
            continue
        kind = classify(d)
        if only or kind in ("keyboard", "buttons"):
            d["class"] = kind
            out.append(d)
    return out


def listen(devs, seconds):
    fds = {}
    for d in devs:
        try:
            fds[os.open("/dev/input/" + d["event"], os.O_RDONLY | os.O_NONBLOCK)] = d
        except PermissionError:
            print("cannot read /dev/input/%s (not in 'input' group?)" % d["event"], file=sys.stderr)
    if not fds:
        return []
    print("Listening on %d devices for %ds. Press the keys you want to identify..." % (len(fds), seconds),
          file=sys.stderr)
    presses, scan = [], {}
    end = time.time() + seconds
    try:
        while time.time() < end:
            r, _, _ = select.select(list(fds), [], [], max(0.0, end - time.time()))
            for fd in r:
                data = os.read(fd, EVENT.size * 64)
                for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                    _, _, typ, code, value = EVENT.unpack_from(data, i)
                    if typ == EV_MSC and code == MSC_SCAN:
                        scan[fd] = value
                    elif typ == EV_KEY and value == 1:
                        d = fds[fd]
                        p = {"event": d["event"], "device": d.get("name"), "code": code,
                             "name": keyname(code), "scancode": "%x" % scan[fd] if fd in scan else None,
                             "keysym": xkb_keysym(code)}
                        presses.append(p)
                        print("  %-8s %-24s code %-4d %-22s scancode %s%s" % (
                            p["event"], (p["device"] or "")[:24], code, p["name"], p["scancode"] or "-",
                            "  keysym %s" % p["keysym"] if p["keysym"] else "  (no default keysym: desktop cannot see it)"),
                            file=sys.stderr, flush=True)
                        scan.pop(fd, None)
    except KeyboardInterrupt:
        pass
    finally:
        for fd in fds:
            os.close(fd)
    return presses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--device", help="eventN; default: all real keyboards and button devices")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("-t", "--seconds", type=int, default=20)
    args = ap.parse_args()

    devs = real_devices(args.device)
    if args.listen:
        presses = listen(devs, args.seconds)
        if args.save:
            store = load_json("keys.json") or {"devices": {}}
            for p in presses:
                dev = next((d for d in devs if d["event"] == p["event"]), {})
                key = "%s %s:%s" % (dev.get("name"), (dev.get("vendor") or "").lower(),
                                    (dev.get("product") or "").lower())
                conf = store.setdefault("confirmed", {}).setdefault(key, {})
                conf[p["name"]] = {"code": p["code"], "scancode": p["scancode"], "confirmed_at": now()}
            store["updated_at"] = now()
            print("Saved " + save_json("keys.json", store), file=sys.stderr)
        emit({"presses": presses}, args.json)
        return

    report = {"scanned_at": now(), "devices": {}}
    for d in devs:
        keys = device_keys(d)
        ident = "%s %s:%s" % (d.get("name"), (d.get("vendor") or "").lower(), (d.get("product") or "").lower())
        report["devices"][ident] = {
            "event": d["event"], "class": d["class"],
            "declared_count": len(keys),
            "declared": [keyname(c) for c in keys],
            "no_keysym": [keyname(c) for c in keys if c > 88 and not xkb_keysym(c)],
        }
    if args.save:
        old = load_json("keys.json") or {}
        report["confirmed"] = old.get("confirmed", {})
        report["saved_to"] = save_json("keys.json", report)
    if emit(report, args.json):
        return
    for ident, d in report["devices"].items():
        print("%s  [%s, %s]  declares %d keys" % (ident, d["event"], d["class"], d["declared_count"]))
        if args.device:
            print("  " + " ".join(d["declared"]))
    if report.get("confirmed"):
        print("\nPhysically confirmed so far:")
        for ident, keys in report["confirmed"].items():
            print("  %s: %s" % (ident, " ".join(sorted(keys))))
    if report.get("saved_to"):
        print("\nSaved " + report["saved_to"])


if __name__ == "__main__":
    main()
