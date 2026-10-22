#!/usr/bin/env python3
"""Check whether this Ubuntu machine can probe keys, inject text and intercept keys.

Reports the session (X11/Wayland, desktop, compositor), which input tools are
installed or installable, whether their services are actually running, uinput
and /dev/input access, keyboard layouts, and a recommended injector and
interceptor for this environment.

  env_check.py            human summary
  env_check.py --json     machine-readable
  env_check.py --save     also write environment.json to the reference store
  env_check.py --install-cmd   print the apt command for missing recommended packages
"""

import argparse
import glob
import grp
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkb_common import emit, have, now, run, save_json  # noqa: E402

# name, apt package, binary, role, note
TOOLS = [
    # injectors: synthesise keystrokes / text
    ("ydotool", "ydotool", "ydotool", "injector",
     "uinput-based; works on any Wayland or X11 session; needs ydotoold; emits keycodes, so layout-sensitive"),
    ("wtype", "wtype", "wtype", "injector",
     "Wayland virtual-keyboard protocol; sends real text; NOT supported by KWin (KDE) or Mutter (GNOME)"),
    ("xdotool", "xdotool", "xdotool", "injector",
     "X11 only; on Wayland reaches XWayland windows at best"),
    ("dotool", "dotool", "dotool", "injector", "uinput-based alternative to ydotool; no daemon"),
    # interceptors: catch a physical key below the desktop and remap it
    ("input-remapper", "input-remapper", "input-remapper-control", "interceptor",
     "per-device key->key/macro mapping, GUI + CLI, works on X11 and Wayland, autoloads presets"),
    ("keyd", "keyd", "keyd", "interceptor",
     "system daemon, text-file config, layers and macros, all keyboards at once"),
    ("kanata", "kanata", "kanata", "interceptor", "QMK-style layers/tap-hold, config file"),
    ("interception-tools", "interception-tools", "intercept", "interceptor",
     "pipeline of small evdev filters (udevmon); for custom plumbing"),
    # diagnostics
    ("evtest", "evtest", "evtest", "diagnostic", "read raw key events from one device"),
    ("libinput", "libinput-tools", "libinput", "diagnostic", "libinput debug-events / list-devices"),
    ("lsusb", "usbutils", "lsusb", "diagnostic", "USB vendor:product inventory"),
    ("wayland-info", "wayland-utils", "wayland-info", "diagnostic",
     "lists compositor protocols; tells you whether wtype can work"),
    ("wev", "wev", "wev", "diagnostic", "Wayland keysym viewer (what the compositor sees)"),
    ("xev", "x11-utils", "xev", "diagnostic", "X11 keysym viewer"),
    ("python3-evdev", "python3-evdev", None, "diagnostic", "Python evdev bindings (nicer key names)"),
]


def apt_candidate(pkg):
    rc, out = run(["apt-cache", "policy", pkg])
    for line in out.splitlines():
        if "Candidate:" in line:
            c = line.split(":", 1)[1].strip()
            return None if c in ("", "(none)") else c
    return None


def dpkg_installed(pkg):
    rc, out = run(["dpkg-query", "-W", "-f=${Status} ${Version}", pkg])
    return out.split()[-1] if rc == 0 and "install ok installed" in out else None


def session():
    s = {
        "session_type": os.environ.get("XDG_SESSION_TYPE") or ("wayland" if os.environ.get("WAYLAND_DISPLAY") else
                                                              "x11" if os.environ.get("DISPLAY") else "tty"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "display": os.environ.get("DISPLAY"),
        "kernel": platform.release(),
    }
    rc, out = run(["lsb_release", "-ds"])
    s["distro"] = out.strip() if rc == 0 else None
    for cmd, key in ((["plasmashell", "--version"], "plasma"), (["gnome-shell", "--version"], "gnome_shell")):
        if have(cmd[0]):
            rc, out = run(cmd)
            if rc == 0:
                s[key] = out.strip().split()[-1]
    return s


def access():
    a = {"user": os.environ.get("USER")}
    try:
        groups = {grp.getgrgid(g).gr_name for g in os.getgroups()}
    except KeyError:
        groups = set()
    a["in_input_group"] = "input" in groups
    a["uinput_writable"] = os.access("/dev/uinput", os.W_OK)
    events = glob.glob("/dev/input/event*")
    a["event_devices"] = len(events)
    a["event_devices_readable"] = sum(os.access(e, os.R_OK) for e in events)
    return a


def services():
    sv = {}
    uid = os.getuid()
    # ydotoold: process + socket, whichever unit started it
    rc, out = run(["pgrep", "-a", "ydotoold"])
    sockets = [p for p in (os.environ.get("YDOTOOL_SOCKET"), "/run/user/%d/.ydotool_socket" % uid,
                           "/tmp/.ydotool_socket") if p and os.path.exists(p)]
    sock_ok = [p for p in sockets if os.access(p, os.W_OK)]
    units = {}
    for scope, unit in (("--user", "ydotool.service"), ("--user", "ydotoold.service"),
                        ("--system", "ydotool.service"), ("--system", "ydotoold.service")):
        rc2, st = run(["systemctl", scope, "is-active", unit])
        if st.strip() in ("active", "activating", "failed"):
            units["%s %s" % (scope.strip("-"), unit)] = st.strip()
    sv["ydotoold"] = {"running": rc == 0, "process": out.strip() or None, "sockets": sockets,
                      "socket_writable": bool(sock_ok), "units": units,
                      "ok": rc == 0 and bool(sock_ok)}
    for name, scope, unit in (("input-remapper", "--system", "input-remapper-daemon.service"),
                              ("keyd", "--system", "keyd.service"),
                              ("kanata", "--user", "kanata.service"),
                              ("espanso", "--user", "espanso.service")):
        rc, st = run(["systemctl", scope, "is-active", unit])
        rc2, en = run(["systemctl", scope, "is-enabled", unit])
        sv[name] = {"unit": "%s %s" % (scope.strip("-"), unit), "active": st.strip(),
                    "enabled": en.strip()}
    return sv


def wtype_viable(sess):
    if sess["session_type"] != "wayland":
        return False, "not a Wayland session"
    if not have("wayland-info"):
        return None, "wayland-info not installed; cannot tell"
    rc, out = run(["wayland-info"], timeout=5)
    ok = "zwp_virtual_keyboard_manager_v1" in out
    return ok, ("compositor advertises zwp_virtual_keyboard_manager_v1" if ok else
                "compositor does not advertise zwp_virtual_keyboard_manager_v1")


def layouts(sess):
    desk = sess["desktop"].upper()
    lay = None
    if "KDE" in desk:
        path = os.path.expanduser("~/.config/kxkbrc")
        if os.path.exists(path):
            for line in open(path):
                if line.startswith("LayoutList="):
                    lay = [x for x in line.strip().split("=", 1)[1].split(",") if x]
        lay = lay or ["(system default)"]
    elif "GNOME" in desk or "UNITY" in desk:
        rc, out = run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"])
        if rc == 0:
            import re
            lay = re.findall(r"\('xkb', '([^']+)'\)", out)
    if lay is None and have("setxkbmap"):
        rc, out = run(["setxkbmap", "-query"])
        for line in out.splitlines():
            if line.startswith("layout:"):
                lay = line.split(":", 1)[1].strip().split(",")
    return lay or []


def recommend(sess, tools, svc, wt, lay):
    rec = {}
    wayland = sess["session_type"] == "wayland"
    if wayland and wt[0]:
        rec["injector"] = ("wtype", "compositor supports the virtual-keyboard protocol; wtype types real text")
    elif tools["ydotool"]["installed"]:
        rec["injector"] = ("ydotool", "uinput route works on every session" +
                           ("" if svc["ydotoold"]["ok"] else "; ydotoold must be started first"))
    elif not wayland and tools["xdotool"]["installed"]:
        rec["injector"] = ("xdotool", "X11 session")
    else:
        rec["injector"] = ("ydotool", "install it: apt install ydotool, then systemctl --user enable --now ydotool")
    if rec["injector"][0] in ("ydotool", "dotool") and len(lay) > 1:
        rec["layout_warning"] = ("%d layouts configured (%s). ydotool emits keycodes, so typed text follows the "
                                 "ACTIVE layout; pin the Latin layout during injection (inject_text.py does this "
                                 "on KDE)." % (len(lay), ",".join(lay)))
    if svc["input-remapper"]["active"] == "active":
        rec["interceptor"] = ("input-remapper", "already running; per-device presets; no extra daemon to add")
    elif svc["keyd"]["active"] == "active":
        rec["interceptor"] = ("keyd", "already running")
    elif tools["input-remapper"]["installable"]:
        rec["interceptor"] = ("input-remapper", "packaged, GUI + CLI, per-device; good default")
    else:
        rec["interceptor"] = ("keyd", "packaged daemon with text config")
    desk = sess["desktop"].upper()
    if "KDE" in desk:
        rec["desktop_binding"] = ("kde-dbus", "register via kglobalaccel D-Bus (bind_kde.py); editing "
                                  "kglobalshortcutsrc by hand does nothing until next login on Plasma 6")
    elif "GNOME" in desk or "UNITY" in desk:
        rec["desktop_binding"] = ("gnome-gsettings", "custom-keybindings via gsettings (bind_gnome.py) apply live")
    else:
        rec["desktop_binding"] = ("interceptor-only", "unknown desktop; bind below the compositor instead")
    return {k: ({"choice": v[0], "why": v[1]} if isinstance(v, tuple) else v) for k, v in rec.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--install-cmd", action="store_true",
                    help="print apt install line for missing injector/interceptor/diagnostic basics")
    args = ap.parse_args()

    sess = session()
    tools = {}
    for name, pkg, binary, role, note in TOOLS:
        inst = dpkg_installed(pkg)
        on_path = have(binary) if binary else bool(inst)
        tools[name] = {"package": pkg, "role": role, "installed": bool(inst or on_path),
                       "version": inst, "installable": bool(inst) or apt_candidate(pkg) is not None,
                       "note": note}
    svc = services()
    wt = wtype_viable(sess)
    lay = layouts(sess)
    acc = access()
    report = {"checked_at": now(), "session": sess, "access": acc, "tools": tools, "services": svc,
              "wtype_viable": {"ok": wt[0], "why": wt[1]}, "layouts": lay}
    report["recommendation"] = recommend(sess, tools, svc, wt, lay)

    problems = []
    if not acc["in_input_group"]:
        problems.append("user not in 'input' group: key probing needs sudo (sudo usermod -aG input $USER, re-login)")
    if not acc["uinput_writable"]:
        problems.append("/dev/uinput not writable: ydotool/dotool need ydotoold or a udev rule")
    if tools["ydotool"]["installed"] and not svc["ydotoold"]["ok"]:
        problems.append("ydotool installed but ydotoold not reachable: systemctl --user enable --now ydotool")
    report["problems"] = problems

    basics = ["ydotool", "evtest", "libinput", "lsusb", "python3-evdev"]
    if sess["session_type"] == "wayland":
        basics.append("wayland-info")
    basics.append(report["recommendation"]["interceptor"]["choice"])
    missing = sorted({tools[t]["package"] for t in basics if not tools[t]["installed"] and tools[t]["installable"]})
    report["install_command"] = ("sudo apt install " + " ".join(missing)) if missing else None

    if args.save:
        report["saved_to"] = save_json("environment.json", report)
    if args.install_cmd:
        print(report["install_command"] or "# nothing to install")
        return
    if emit(report, args.json):
        return

    print("Session   %s / %s %s  (%s)" % (sess["session_type"], sess["desktop"],
                                          sess.get("plasma") or sess.get("gnome_shell") or "", sess["distro"]))
    print("Access    input group: %s   /dev/uinput writable: %s   readable event devices: %d/%d" % (
        acc["in_input_group"], acc["uinput_writable"], acc["event_devices_readable"], acc["event_devices"]))
    print("Layouts   %s" % (", ".join(lay) or "unknown"))
    print("wtype     %s" % wt[1])
    print("\nTools")
    for role in ("injector", "interceptor", "diagnostic"):
        for name, t in tools.items():
            if t["role"] == role:
                state = "installed" if t["installed"] else ("installable" if t["installable"] else "not packaged")
                print("  %-12s %-19s %-13s %s" % (role, name, state, t["note"]))
    print("\nServices")
    y = svc["ydotoold"]
    print("  ydotoold         running=%s socket_writable=%s %s" % (y["running"], y["socket_writable"],
                                                                   " ".join(y["sockets"])))
    for name in ("input-remapper", "keyd", "kanata", "espanso"):
        s = svc[name]
        print("  %-16s %s (%s) [%s]" % (name, s["active"], s["enabled"], s["unit"]))
    print("\nRecommendation")
    for k, v in report["recommendation"].items():
        print("  %-16s %s" % (k, v if isinstance(v, str) else "%s - %s" % (v["choice"], v["why"])))
    if problems:
        print("\nProblems")
        for p in problems:
            print("  - " + p)
    if report["install_command"]:
        print("\nInstall   " + report["install_command"])
    if args.save:
        print("\nSaved     " + report["saved_to"])


if __name__ == "__main__":
    main()
