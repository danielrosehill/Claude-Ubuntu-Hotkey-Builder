---
name: check-environment
description: Check whether an Ubuntu machine can probe keys, inject text and intercept keys - session type (X11/Wayland), desktop (KDE/GNOME), which injectors (ydotool, wtype, xdotool) and interceptors (input-remapper, keyd, kanata) are installed or installable, whether ydotoold / input-remapper-daemon / keyd are actually running, input-group and /dev/uinput access, keyboard layouts - then install what is missing and recommend an injector and an interceptor. Use before creating any shortcut or macro, when "ydotool does nothing", "is input-remapper running", "what can I use to type text from a hotkey", or "set up my machine for key macros".
---

# Check the input environment

Locate the scripts first. Every skill in this plugin uses the same line:

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
```

## 1. Run the check and save it to the reference

```bash
python3 "$HKB/env_check.py" --save
```

It writes `environment.json` to the per-machine reference
(`python3 "$HKB/reference.py" path` shows where). Read the output for:

- **Session** - Wayland or X11, desktop and version. This picks the binding route.
- **Access** - in the `input` group, `/dev/uinput` writable. Without the group,
  key probing needs sudo and ydotool cannot reach uinput.
- **wtype** - whether the compositor advertises `zwp_virtual_keyboard_manager_v1`.
  KWin and Mutter do not; do not recommend wtype there.
- **Layouts** - more than one layout means ydotool output follows the active
  one. Say so whenever text injection is the goal.
- **Services** - `ydotoold` must be running *and* its socket writable. A
  service that is `active` but whose socket the user cannot write is not working.
- **Recommendation** - injector, interceptor, desktop binding route.

## 2. Fix what is missing

Ask before installing (it uses sudo), then:

```bash
python3 "$HKB/env_check.py" --install-cmd     # prints e.g. sudo apt install ydotool evtest
```

Run the printed command. Package availability was checked live with
`apt-cache policy`, so a tool reported "not packaged" needs another source -
say so rather than guessing a PPA.

Start services:

| Tool | Command | Notes |
| --- | --- | --- |
| ydotoold | `systemctl --user enable --now ydotool` | Ubuntu ships this user unit; socket at `$XDG_RUNTIME_DIR/.ydotool_socket` |
| input-remapper | `sudo systemctl enable --now input-remapper-daemon` | system service; GUI is `input-remapper-gtk` |
| keyd | `sudo systemctl enable --now keyd` | config in `/etc/keyd/*.conf`; affects all keyboards |
| input group | `sudo usermod -aG input "$USER"` | takes effect at next login |

Re-run `env_check.py --save` and confirm the problem list is empty. Do not
report a service as fixed from `systemctl is-active` alone: the script checks
the socket, which is what actually has to work.

## 3. Suggest an interceptor when one is needed

An interceptor is needed when the key is invisible to the desktop (no keysym),
is a keypad key on KDE, or should behave identically on every desktop and the
console. Prefer, in order:

1. one already running (input-remapper or keyd) - never add a second grabber
   to the same keyboard;
2. **input-remapper** - per-device, GUI + CLI, presets autoload, no config
   language to learn;
3. **keyd** - one text file for all keyboards, layers, good for many remaps;
4. **kanata** - for QMK-style tap-hold and layers.

Two grabbers on one device fight: whichever grabs first wins and the other sees
nothing. Check `services` in the report before installing another.

See `references/routes.md` for the facts behind each recommendation.
