#!/usr/bin/env python3
"""Bind a key to a command as a GNOME custom keyboard shortcut (applies live).

GNOME keeps custom shortcuts in gsettings under
org.gnome.settings-daemon.plugins.media-keys custom-keybindings, a list of
paths, each a relocatable schema with name / command / binding. Writing them
with gsettings takes effect immediately - no logout, unlike KDE's config file.

  bind_gnome.py --bind KEY_PAUSE --name "Type claude" --command "hkb-type --enter claude"
  bind_gnome.py --bind "<Super><Alt>c" --name ... --command ...   (accelerator syntax also accepted)
  bind_gnome.py --unbind type_claude
  bind_gnome.py --list
"""

import argparse
import ast
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import keycode, xkb_keysym  # noqa: E402

BASE = "org.gnome.settings-daemon.plugins.media-keys"
REL = BASE + ".custom-keybinding"
ROOT = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PREFIX = "hkb_"


def gs(*args):
    p = subprocess.run(["gsettings"] + list(args), capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("gsettings %s failed: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def paths():
    raw = gs("get", BASE, "custom-keybindings")
    raw = re.sub(r"^@as ", "", raw)
    return list(ast.literal_eval(raw)) if raw.startswith("[") else []


def set_paths(lst):
    gs("set", BASE, "custom-keybindings", str(lst))


def accel(key):
    if key.startswith("<") or not key.upper().startswith("KEY_"):
        return key
    sym = xkb_keysym(keycode(key))
    if not sym:
        raise SystemExit("%s has no default keysym; GNOME cannot see it. Use an interceptor." % key)
    return sym


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def existing_owner(binding):
    for p in paths():
        if gs("get", REL + ":" + p, "binding").strip("'") == binding:
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bind", metavar="KEY")
    g.add_argument("--unbind", metavar="NAME")
    g.add_argument("--list", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--command")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.list:
        for p in paths():
            s = REL + ":" + p
            print("  %-60s %-20s %s" % (p, gs("get", s, "binding"), gs("get", s, "command")))
        return
    if args.unbind:
        path = ROOT + PREFIX + slugify(args.unbind) + "/"
        set_paths([p for p in paths() if p != path])
        subprocess.run(["dconf", "reset", "-f", path], capture_output=True)
        print("removed " + path)
        return
    if not (args.name and args.command):
        ap.error("--bind needs --name and --command")
    binding = accel(args.bind)
    owner = existing_owner(binding)
    path = ROOT + PREFIX + slugify(args.name) + "/"
    if owner and owner != path and not args.force:
        raise SystemExit("%s already bound by %s (pass --force to add anyway)" % (binding, owner))
    s = REL + ":" + path
    gs("set", s, "name", args.name)
    gs("set", s, "command", args.command)
    gs("set", s, "binding", binding)
    lst = paths()
    if path not in lst:
        set_paths(lst + [path])
    print("bound %s -> %s (%s)" % (binding, args.command, path))


if __name__ == "__main__":
    main()
