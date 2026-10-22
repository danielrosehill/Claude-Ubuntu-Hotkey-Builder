#!/usr/bin/env python3
"""Type text into the focused window, on whatever this session supports.

Self-contained (standard library only) so it can be installed outside the
plugin, e.g. as ~/.local/bin/hkb-type, and called from a shortcut:

  hkb-type --enter claude          types "claude" then presses Enter
  hkb-type --dry-run "git status"  prints the backend and commands, types nothing

Backends, tried in order unless HKB_INJECTOR / --backend forces one:
  wtype    Wayland virtual-keyboard protocol; types real characters, layout-proof.
           KWin and Mutter do not implement it; wlroots compositors do.
  ydotool  /dev/uinput via ydotoold; works everywhere, but sends US-layout
           keycodes, so on KDE the Latin layout is pinned for the duration.
  xdotool  X11 sessions.

Layout pinning (KDE only): with several layouts configured, ydotool output
follows the active one (Hebrew active -> Hebrew letters). --layout N (default:
first layout in kxkbrc that is not in a known non-Latin list) is selected over
D-Bus before typing and the previous layout restored afterwards.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

NON_LATIN = {"il", "ru", "ua", "by", "bg", "mk", "rs", "gr", "ara", "ir", "af", "pk", "th", "jp", "kr", "cn",
             "in", "bd", "np", "lk", "et", "ge", "am", "kz", "kg", "mn", "tj", "iq", "sy", "eg"}
KEY_ENTER = 28


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, dry, stdin=None):
    if dry:
        print("  $ " + " ".join(cmd) + ("   <<< %r" % stdin if stdin is not None else ""))
        return 0
    return subprocess.run(cmd, input=stdin, text=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE).returncode


def wtype_works():
    if os.environ.get("XDG_SESSION_TYPE") != "wayland" or not have("wtype"):
        return False
    # wtype with no text still connects and fails fast without the protocol
    p = subprocess.run(["wtype", ""], capture_output=True, text=True)
    return p.returncode == 0


def ydotool_ready():
    if not have("ydotool"):
        return False
    sock = os.environ.get("YDOTOOL_SOCKET") or "/run/user/%d/.ydotool_socket" % os.getuid()
    return os.path.exists(sock) or os.path.exists("/tmp/.ydotool_socket")


def kde_layouts():
    path = os.path.expanduser("~/.config/kxkbrc")
    try:
        for line in open(path):
            if line.startswith("LayoutList="):
                return [x for x in line.strip().split("=", 1)[1].split(",") if x]
    except OSError:
        pass
    return []


def qdbus():
    for q in ("qdbus6", "qdbus"):
        if have(q):
            return q
    return None


def kde_get_layout():
    q = qdbus()
    if not q:
        return None
    p = subprocess.run([q, "org.kde.keyboard", "/Layouts", "org.kde.KeyboardLayouts.getLayout"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        p = subprocess.run([q, "org.kde.KWin", "/Layouts", "org.kde.KeyboardLayouts.getLayout"],
                           capture_output=True, text=True)
    try:
        return int(p.stdout.strip())
    except ValueError:
        return None


def kde_set_layout(idx, dry):
    q = qdbus()
    if not q:
        return
    for service in ("org.kde.keyboard", "org.kde.KWin"):
        if run([q, service, "/Layouts", "org.kde.KeyboardLayouts.setLayout", str(idx)], dry) == 0:
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--enter", action="store_true", help="press Enter after the text")
    ap.add_argument("--backend", default=os.environ.get("HKB_INJECTOR", "auto"),
                    choices=("auto", "wtype", "ydotool", "xdotool"))
    ap.add_argument("--layout", type=int, default=None, help="KDE layout index to pin while typing")
    ap.add_argument("--delay", type=int, default=int(os.environ.get("HKB_DELAY_MS", "80")),
                    help="ms to wait first, so the trigger key is released (default 80)")
    ap.add_argument("--key-delay", type=int, default=6, help="ms between keystrokes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    backend = args.backend
    if backend == "auto":
        if wtype_works():
            backend = "wtype"
        elif ydotool_ready():
            backend = "ydotool"
        elif os.environ.get("DISPLAY") and have("xdotool") and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            backend = "xdotool"
        else:
            sys.exit("hkb-type: no working injector (install ydotool and run: systemctl --user enable --now ydotool)")
    if args.dry_run:
        print("backend: " + backend)

    pinned_from = None
    if backend == "ydotool" and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        layouts = kde_layouts()
        if len(layouts) > 1:
            want = args.layout
            if want is None:
                want = next((i for i, l in enumerate(layouts) if l.split("(")[0] not in NON_LATIN), 0)
            cur = kde_get_layout()
            if cur is not None and cur != want:
                pinned_from = cur
                kde_set_layout(want, args.dry_run)

    if not args.dry_run:
        time.sleep(args.delay / 1000.0)
    try:
        if backend == "wtype":
            cmd = ["wtype", "-d", str(args.key_delay), args.text] if args.text else []
            if args.enter:
                cmd = (cmd or ["wtype"]) + ["-k", "Return"]
            if cmd:
                run(cmd, args.dry_run)
        elif backend == "ydotool":
            if args.text:
                # text on stdin: ydotool interprets backslash escapes in arguments, not in files
                run(["ydotool", "type", "-d", str(args.key_delay), "-H", str(args.key_delay), "-f", "-"],
                    args.dry_run, stdin=args.text)
            if args.enter:
                run(["ydotool", "key", "%d:1" % KEY_ENTER, "%d:0" % KEY_ENTER], args.dry_run)
        elif backend == "xdotool":
            if args.text:
                run(["xdotool", "type", "--delay", str(args.key_delay), "--", args.text], args.dry_run)
            if args.enter:
                run(["xdotool", "key", "Return"], args.dry_run)
    finally:
        if pinned_from is not None:
            if not args.dry_run:
                time.sleep(0.05)
            kde_set_layout(pinned_from, args.dry_run)


if __name__ == "__main__":
    main()
