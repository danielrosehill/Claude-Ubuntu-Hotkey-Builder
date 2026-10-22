#!/usr/bin/env python3
"""Bind a single key to a command as a KDE Plasma 6 global shortcut - live, no logout.

Plasma 6 has no kglobalacceld: KWin serves org.kde.kglobalaccel itself and never
re-reads kglobalshortcutsrc, so editing that file does nothing until the next
login. This registers over D-Bus the way the Shortcuts KCM does: a hidden
.desktop launcher, doRegister, then setForeignShortcut with the Qt key int.

  bind_kde.py --check KEY_PAUSE                     who owns this key right now (live)
  bind_kde.py --verify KEY_PAUSE [-t 20]            prove KWin fires on it: temp binding, you press the key
  bind_kde.py --bind KEY_PAUSE --name "Type claude" --command "hkb-type --enter claude"
  bind_kde.py --unbind type_claude                  remove a binding made by this script
  bind_kde.py --list                                bindings made by this script

Verification needs a PHYSICAL press. Keys synthesised through ydotool fired
neither a launcher registered here (Pause, F9) nor powerdevil's own keyboard-
light shortcut, although evdev showed the events arriving (Plasma 6.6.6,
2026-10-22; cause not established). A synthetic test is a false negative.

KWin launches a .desktop shortcut only if KService already knows the file when
the shortcut is registered: a launcher registered before kbuildsycoca6 has run
is stored under [services] and looks fine, but never launches. So the order is
write .desktop -> kbuildsycoca6 -> doRegister -> setForeignShortcut.
"""

import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import keycode, keyname, now, qt_key, xkb_keysym  # noqa: E402

APPS = os.path.expanduser("~/.local/share/applications")
PREFIX = "hkb_"  # D-Bus object paths cannot contain '-', so neither can the desktop file name
GDBUS = ["gdbus", "call", "--session", "--dest", "org.kde.kglobalaccel", "--object-path", "/kglobalaccel",
         "--method"]


def gcall(method, *args):
    p = subprocess.run(GDBUS + ["org.kde.KGlobalAccel." + method] + list(args), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("%s failed: %s" % (method, p.stderr.strip()))
    return p.stdout.strip()


def resolve(key):
    code = keycode(key)
    sym = xkb_keysym(code)
    q = qt_key(sym)
    if q is None:
        raise SystemExit("%s (code %d, keysym %s) cannot be bound on KDE: %s. Use an interceptor, or the "
                         "two-stage route onto KEY_F14-F18." % (
                             keyname(code), code, sym,
                             "no default keysym" if not sym else "kglobalaccel has no encoding for it"))
    if q & 0x20000000:
        print("warning: %s is a keypad key; KWin 6.6 registers keypad shortcuts but does not fire them. "
              "Run --verify before relying on it." % keyname(code), file=sys.stderr)
    return code, sym, q


def owners(q):
    out = gcall("getGlobalShortcutsByKey", str(q))
    # (@a(ssssssaiai) [],)  or  ([('action', 'Friendly', 'comp.desktop', 'Comp', ...)],)
    found = re.findall(r"\('([^']*)', '([^']*)', '([^']*)', '([^']*)'", out)
    return [{"component": c, "action": a, "friendly": "%s: %s" % (cf, af)} for a, af, c, cf in found]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def write_desktop(slug, name, command):
    os.makedirs(APPS, exist_ok=True)
    path = os.path.join(APPS, PREFIX + slug + ".desktop")
    with open(path, "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nNoDisplay=true\n"
                "X-HKB-Created=%s\n" % (name, command, now()))
    subprocess.run(["update-desktop-database", APPS], capture_output=True)
    for tool in ("kbuildsycoca6", "kbuildsycoca5"):
        if subprocess.run(["sh", "-c", "command -v " + tool], capture_output=True).returncode == 0:
            subprocess.run([tool], capture_output=True)
            break
    return path


def action_id(slug, name):
    comp = PREFIX + slug + ".desktop"
    return comp, "['%s','_launch','%s','%s']" % (comp, name.replace("'", ""), name.replace("'", ""))


def bind(key, name, command, force=False):
    code, sym, q = resolve(key)
    taken = owners(q)
    slug = slugify(name)
    comp, aid = action_id(slug, name)
    others = [o for o in taken if o["component"] != comp]
    if others and not force:
        raise SystemExit("%s is already bound: %s. Choose another key or pass --force." % (
            keyname(code), "; ".join(o["friendly"] for o in others)))
    path = write_desktop(slug, name, command)
    gcall("doRegister", aid)
    gcall("setForeignShortcut", aid, "[%d]" % q)
    after = owners(q)
    ok = any(o["component"] == comp for o in after)
    print("%s %s (keysym %s, Qt %d) -> %s\n  launcher %s\n  registered live: %s" % (
        "bound" if ok else "FAILED to bind", keyname(code), sym, q, command, path, ok))
    return ok


def unbind(slug):
    comp = PREFIX + slugify(slug) + ".desktop"
    path = os.path.join(APPS, comp)
    try:
        aid = "['%s','_launch','','']" % comp
        gcall("setForeignShortcut", aid, "[]")
        gcall("unregister", comp, "_launch")
    except RuntimeError as e:
        print("note: " + str(e), file=sys.stderr)
    if os.path.exists(path):
        os.remove(path)
    print("removed " + comp)


def verify(key, seconds=20):
    """Bind the key to a marker command, wait for a physical press, see whether it fired."""
    code, sym, q = resolve(key)
    taken = owners(q)
    if taken:
        raise SystemExit("%s is taken by %s; nothing to verify." % (keyname(code),
                                                                     "; ".join(o["friendly"] for o in taken)))
    marker = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hkb-verify-%d" % os.getpid())
    name = "hkb verify"
    try:
        bind(key, name, "touch %s" % marker)
        print("Press %s now (waiting %ds)..." % (keyname(code), seconds), flush=True)
        for _ in range(seconds * 10):
            if os.path.exists(marker):
                break
            time.sleep(0.1)
        fired = os.path.exists(marker)
    finally:
        unbind(name)
        if os.path.exists(marker):
            os.remove(marker)
    print("%s: KWin %s the shortcut" % (keyname(code), "FIRED" if fired else "did NOT fire"))
    return fired


def list_ours():
    if not os.path.isdir(APPS):
        return
    for f in sorted(os.listdir(APPS)):
        if f.startswith(PREFIX) and f.endswith(".desktop"):
            text = open(os.path.join(APPS, f)).read()
            ex = re.search(r"^Exec=(.*)$", text, re.M)
            out = gcall("shortcut", "['%s','_launch','','']" % f)
            keys = re.findall(r"\d+", out)
            print("  %-34s keys=%-12s %s" % (f, ",".join(keys) or "-", ex.group(1) if ex else ""))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", metavar="KEY")
    g.add_argument("--verify", metavar="KEY")
    g.add_argument("--bind", metavar="KEY")
    g.add_argument("--unbind", metavar="NAME")
    g.add_argument("--list", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--command")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-t", "--seconds", type=int, default=20)
    args = ap.parse_args()

    if args.check:
        code, sym, q = resolve(args.check)
        o = owners(q)
        print("%s (keysym %s, Qt %d): %s" % (keyname(code), sym, q,
                                             "; ".join(x["friendly"] for x in o) if o else "free"))
    elif args.verify:
        sys.exit(0 if verify(args.verify, args.seconds) else 1)
    elif args.bind:
        if not (args.name and args.command):
            ap.error("--bind needs --name and --command")
        sys.exit(0 if bind(args.bind, args.name, args.command, args.force) else 1)
    elif args.unbind:
        unbind(args.unbind)
    else:
        list_ours()


if __name__ == "__main__":
    main()
