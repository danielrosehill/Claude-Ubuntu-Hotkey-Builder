#!/usr/bin/env python3
"""Inventory input-capable hardware: lsusb plus every evdev input device.

Records vendor:product IDs, bus, the /dev/input/eventN node, a device class
(keyboard / pointer / buttons / virtual), how many keys the driver declares,
and a stable by-id path where one exists. The by-id path and VID:PID survive
replugging; eventN numbers do not, so bindings should be keyed on those.

  usb_inventory.py           human table
  usb_inventory.py --json
  usb_inventory.py --save    write devices.json (and diff against the last save)
"""

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import (BUSTYPES, classify, device_keys, emit, have, load_json,  # noqa: E402
                        now, run, save_json)


def lsusb():
    out = []
    if not have("lsusb"):
        return out
    rc, text = run(["lsusb"])
    for line in text.splitlines():
        m = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-f]{4}):([0-9a-f]{4})\s*(.*)", line)
        if m:
            out.append({"bus": m.group(1), "device": m.group(2), "vid": m.group(3), "pid": m.group(4),
                        "description": m.group(5).strip(),
                        "root_hub": m.group(3) == "1d6b"})
    return out


def by_id_links():
    links = {}
    for pattern in ("/dev/input/by-id/*", "/dev/input/by-path/*"):
        for link in glob.glob(pattern):
            target = os.path.basename(os.path.realpath(link))
            if target.startswith("event"):
                links.setdefault(target, []).append(link)
    return links


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    from hkb_common import input_devices
    links = by_id_links()
    devices = []
    for d in input_devices():
        if not d.get("event"):
            continue
        keys = device_keys(d)
        kind = classify(d)
        devices.append({
            "name": d.get("name"),
            "event": d["event"],
            "vid": (d.get("vendor") or "").lower(),
            "pid": (d.get("product") or "").lower(),
            "bus": "virtual (uinput)" if kind == "virtual" else
                   BUSTYPES.get((d.get("bustype") or "").lower(), d.get("bustype")),
            "class": kind,
            "declared_keys": len(keys),
            "phys": d.get("phys"),
            "stable_paths": sorted(links.get(d["event"], [])),
        })
    report = {"scanned_at": now(), "usb": lsusb(), "input_devices": devices}

    if args.save:
        old = load_json("devices.json") or {}
        old_ids = {(x["vid"], x["pid"], x["name"]) for x in old.get("input_devices", [])}
        new_ids = {(x["vid"], x["pid"], x["name"]) for x in devices}
        report["changes_since_last_save"] = {
            "added": sorted("%s:%s %s" % t for t in new_ids - old_ids),
            "removed": sorted("%s:%s %s" % t for t in old_ids - new_ids),
            "previous_scan": old.get("scanned_at"),
        }
        report["saved_to"] = save_json("devices.json", report)

    if emit(report, args.json):
        return
    print("USB (lsusb, root hubs hidden)")
    for u in report["usb"]:
        if not u["root_hub"]:
            print("  %s:%s  bus %s dev %s  %s" % (u["vid"], u["pid"], u["bus"], u["device"], u["description"]))
    print("\nInput devices")
    print("  %-8s %-10s %-9s %-17s %5s  %s" % ("node", "vid:pid", "class", "bus", "keys", "name"))
    for d in devices:
        print("  %-8s %s:%s %-9s %-17s %5d  %s" % (d["event"], d["vid"], d["pid"], d["class"], d["bus"],
                                                   d["declared_keys"], d["name"]))
    if args.save:
        ch = report["changes_since_last_save"]
        if ch["previous_scan"]:
            print("\nSince %s: +%d -%d" % (ch["previous_scan"], len(ch["added"]), len(ch["removed"])))
            for x in ch["added"]:
                print("  + " + x)
            for x in ch["removed"]:
                print("  - " + x)
        print("\nSaved " + report["saved_to"])


if __name__ == "__main__":
    main()
