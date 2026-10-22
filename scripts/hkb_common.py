"""Shared helpers for the hotkey-builder scripts.

Standard library only. python3-evdev is used for key names when present, but
nothing depends on it.
"""

import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys

PLUGIN = "hotkey-builder"

# evdev keycodes above this have no X11 keycode. On Wayland xkbcommon can still
# give them a keysym (KEY_FAVORITES -> XF86Favorites), so visibility is decided
# by xkb_keysym() below, not by this number; it only matters on an X11 session.
X11_MAX_KEYCODE = 247


# ---------------------------------------------------------------- paths

def data_root():
    """Resolve the user-data root and say which rule chose it.

    override ($HKB_DATA_DIR) -> $CLAUDE_USER_DATA -> first existing of
    ~/.claude-user-data, ${XDG_DATA_HOME:-~/.local/share}/claude-plugins
    -> default ~/.claude-user-data. Existing roots are adopted, never migrated.
    """
    home = os.path.expanduser("~")
    if os.environ.get("HKB_DATA_DIR"):
        return os.environ["HKB_DATA_DIR"], "HKB_DATA_DIR"
    if os.environ.get("CLAUDE_USER_DATA"):
        return os.path.join(os.environ["CLAUDE_USER_DATA"], PLUGIN), "CLAUDE_USER_DATA"
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    for root in (os.path.join(home, ".claude-user-data"), os.path.join(xdg, "claude-plugins")):
        if os.path.isdir(root):
            return os.path.join(root, PLUGIN), "existing root " + root
    return os.path.join(home, ".claude-user-data", PLUGIN), "default"


def host_dir():
    """Per-machine reference folder: <root>/<hostname>/."""
    root, _ = data_root()
    path = os.path.join(root, socket.gethostname())
    os.makedirs(path, exist_ok=True)
    return path


def save_json(name, obj):
    path = os.path.join(host_dir(), name)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.write("\n")
    return path


def load_json(name, default=None):
    path = os.path.join(host_dir(), name)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- shell

def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, timeout=10):
    """Run a command, return (rc, stdout). Never raises for a missing binary."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           shell=isinstance(cmd, str))
        return p.returncode, (p.stdout or "") + (p.stderr if p.returncode else "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def emit(obj, as_json):
    if as_json:
        json.dump(obj, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return True
    return False


# ---------------------------------------------------------------- key names

_KEYNAMES = None
# Range markers and legacy spellings that share a code with the real key name.
_ALIASES = {"KEY_MIN_INTERESTING", "KEY_HANGUEL", "KEY_SCREENLOCK", "KEY_BRIGHTNESS_ZERO",
            "KEY_WIMAX", "KEY_ROTATE_LOCK_TOGGLE", "BTN_MISC", "BTN_MOUSE", "BTN_JOYSTICK",
            "BTN_GAMEPAD", "BTN_DIGI", "BTN_WHEEL", "BTN_TRIGGER_HAPPY"}


def _pick_alias(name):
    if not isinstance(name, (list, tuple)):
        return name
    real = [n for n in name if n not in _ALIASES]
    return (real or list(name))[0]


def keynames():
    """Map evdev keycode -> KEY_*/BTN_* name."""
    global _KEYNAMES
    if _KEYNAMES is not None:
        return _KEYNAMES
    names = {}
    try:
        from evdev import ecodes  # python3-evdev
        for table in (ecodes.KEY, ecodes.BTN):
            for code, name in table.items():
                names.setdefault(code, _pick_alias(name))
    except ImportError:
        header = "/usr/include/linux/input-event-codes.h"
        if os.path.exists(header):
            pat = re.compile(r"#define\s+((?:KEY|BTN)_[A-Z0-9_]+)\s+(0x[0-9a-fA-F]+|\d+)")
            for line in open(header):
                m = pat.match(line)
                if m:
                    names.setdefault(int(m.group(2), 0), m.group(1))
    _KEYNAMES = names
    return names


def keyname(code):
    return keynames().get(code, "KEY_%d" % code)


def keycode(name):
    """KEY_F13 / f13 / 183 -> 183."""
    if isinstance(name, int) or str(name).isdigit():
        return int(name)
    want = str(name).upper()
    if not want.startswith(("KEY_", "BTN_")):
        want = "KEY_" + want
    for code, n in keynames().items():
        if n == want:
            return code
    raise KeyError(name)


# ---------------------------------------------------------------- input devices

def input_devices():
    """Parse /proc/bus/input/devices into a list of dicts."""
    devs, cur = [], {}
    try:
        text = open("/proc/bus/input/devices").read()
    except OSError:
        return devs
    for line in text.splitlines() + [""]:
        if not line.strip():
            if cur:
                devs.append(cur)
            cur = {}
            continue
        tag, _, rest = line.partition(": ")
        if tag == "I":
            kv = dict(p.split("=", 1) for p in rest.split())
            cur.update(bustype=kv.get("Bus"), vendor=kv.get("Vendor"),
                       product=kv.get("Product"), version=kv.get("Version"))
        elif tag == "N":
            cur["name"] = rest.split("=", 1)[1].strip('"')
        elif tag == "P":
            cur["phys"] = rest.split("=", 1)[1]
        elif tag == "S":
            cur["sysfs"] = rest.split("=", 1)[1]
        elif tag == "U":
            cur["uniq"] = rest.split("=", 1)[1]
        elif tag == "H":
            handlers = rest.split("=", 1)[1].split()
            cur["handlers"] = handlers
            cur["event"] = next((h for h in handlers if h.startswith("event")), None)
        elif tag == "B":
            k, v = rest.split("=", 1)
            cur.setdefault("bits", {})[k] = v
    return devs


def bitmap_codes(hexwords):
    """Decode a sysfs capability bitmap ("70000 0 ... fffe") into a set of bit indices."""
    import struct
    words = hexwords.split()
    codes = set()
    # The kernel prints one C long per word, leading zeros stripped.
    width = struct.calcsize("l") * 8
    for i, w in enumerate(reversed(words)):
        val = int(w, 16)
        bit = 0
        while val:
            if val & 1:
                codes.add(i * width + bit)
            val >>= 1
            bit += 1
    return codes


def device_keys(dev):
    return sorted(bitmap_codes(dev.get("bits", {}).get("KEY", "")))


BUSTYPES = {"0003": "usb", "0005": "bluetooth", "0011": "i8042 (built-in)",
            "0019": "host (platform)", "0006": "virtual", "0018": "i2c", "001e": "spi"}


def classify(dev):
    """Rough device class from name and capabilities."""
    name = (dev.get("name") or "").lower()
    keys = set(device_keys(dev))
    # uinput devices often claim bus 0003 (usb); the sysfs path does not lie.
    virtual = (dev.get("sysfs") or "").startswith("/devices/virtual/") or any(
        s in name for s in ("virtual", "uinput", "ydotool", "input-remapper", "espanso", "keyd"))
    letters = {30, 48, 46, 32, 18}  # a b c d e
    if virtual:
        kind = "virtual"
    elif letters <= keys:
        kind = "keyboard"
    elif 272 in keys:  # BTN_LEFT
        kind = "pointer"
    elif keys:
        kind = "buttons"
    else:
        kind = "other"
    return kind


# ---------------------------------------------------------------- xkb keysyms

_XKB = None
XKB_DIR = "/usr/share/X11/xkb"


def _xkb_tables():
    """(code -> key name, key name -> first active keysym) from the default xkb data.

    Approximation of the default "evdev" ruleset: keycodes/evdev for names,
    symbols/pc then symbols/inet for keysyms, first active definition wins.
    The live test in bind_kde.py --verify is the authority; this is the
    prediction that decides which route to try first.
    """
    global _XKB
    if _XKB is not None:
        return _XKB
    names, syms = {}, {}
    try:
        for line in open(os.path.join(XKB_DIR, "keycodes", "evdev")):
            line = line.split("//")[0]
            m = re.match(r"\s*<([A-Z0-9+-]+)>\s*=\s*(\d+);", line)
            if m:
                names.setdefault(int(m.group(2)), m.group(1))
                continue
            m = re.match(r"\s*alias\s*<([A-Z0-9]+)>\s*=\s*<([A-Z0-9]+)>;", line)
            if m:
                syms.setdefault("alias:" + m.group(1), m.group(2))
        for n in range(1, 13):  # srvr_ctrl(fkey2vt): F1-F12 plus VT switching
            syms["FK%02d" % n] = "F%d" % n
        # inet(evdev) is the ruleset's media/vendor-key section; other inet
        # sections are per-vendor overrides and would give wrong answers.
        for f, section in (("inet", "evdev"), ("pc", None), ("keypad", None)):
            inside = section is None
            for line in open(os.path.join(XKB_DIR, "symbols", f)):
                line = line.split("//")[0]
                head = re.match(r'\s*(?:\w+\s+)*xkb_symbols\s+"([^"]+)"', line)
                if head:
                    inside = section is None or head.group(1) == section
                    continue
                if not inside:
                    continue
                m = re.match(r"\s*key\s*<([A-Z0-9+-]+)>\s*\{[^\[]*\[\s*([A-Za-z0-9_]+)", line)
                if m:
                    syms.setdefault(m.group(1), m.group(2))
    except OSError:
        pass
    _XKB = (names, syms)
    return _XKB


def xkb_keysym(code):
    """Default keysym the desktop will see for evdev `code`, or None if it has none.

    Letter and punctuation keys come from the layout file and return None here;
    they are never shortcut candidates, so that is not looked up.

    A key with no keysym is invisible to every desktop shortcut system and to
    applications; only /dev/input readers (input-remapper, keyd) can use it.
    """
    names, syms = _xkb_tables()
    name = names.get(code + 8)
    if name is None:
        return None
    for cand in (name, syms.get("alias:" + name)):
        if cand and cand in syms:
            return syms[cand]
    # keycodes/evdev names <FKnn> via alias <I191> etc.; try the reverse alias
    for k, v in syms.items():
        if k.startswith("alias:") and v == name and k[6:] in syms:
            return syms[k[6:]]
    return None


# keysym -> Qt key int, as kglobalaccel expects it (verified against Qt 6 QKeySequence).
_QT_NAMED = {"Insert": 0x1000006, "Delete": 0x1000007, "Pause": 0x1000008, "Print": 0x1000009,
             "Home": 0x1000010, "End": 0x1000011, "Prior": 0x1000016, "Next": 0x1000017,
             "Caps_Lock": 0x1000024, "Num_Lock": 0x1000025, "Scroll_Lock": 0x1000026, "Menu": 0x1000055,
             "XF86Tools": 0x10000f1, "XF86Favorites": 0x1000091, "XF86Keyboard": 0x100011f,
             "XF86Calculator": 0x10000cb, "XF86Messenger": 0x10000f9, "XF86Phone": 0x10000e3,
             "XF86Search": 0x1000092}
_QT_KEYPAD = {"KP_Divide": 0x2000002f, "KP_Multiply": 0x2000002a, "KP_Subtract": 0x2000002d,
              "KP_Add": 0x2000002b, "KP_Enter": 0x21000005}


def qt_key(keysym):
    """Qt key int for a keysym name, or None if unknown."""
    if not keysym:
        return None
    m = re.fullmatch(r"F(\d+)", keysym)
    if m and 1 <= int(m.group(1)) <= 35:
        return 0x1000030 + int(m.group(1)) - 1
    m = re.fullmatch(r"XF86Launch([0-9A-F])", keysym)
    if m:
        return 0x10000a2 + int(m.group(1), 16)
    return _QT_NAMED.get(keysym) or _QT_KEYPAD.get(keysym)
