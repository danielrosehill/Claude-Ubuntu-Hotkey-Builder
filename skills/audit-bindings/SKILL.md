---
name: audit-bindings
description: Audit every existing claim on a key on Ubuntu, across all layers - udev hwdb kernel remaps, keyd, input-remapper presets (and which are autoloaded), KDE global shortcuts (kglobalshortcutsrc plus the live kglobalaccel D-Bus answer), GNOME keybindings and custom shortcuts, xbindkeys/sxhkd, kanata, and manual reservations - normalised to evdev key names. Use for "what is this key bound to", "is F9 free", "find shortcut conflicts", "list my keyboard shortcuts", or before creating any new binding.
---

# Audit existing bindings

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
python3 "$HKB/bindings_audit.py" --save            # everything
python3 "$HKB/bindings_audit.py" --key KEY_F9      # one key
```

Each claim: source, `1-key` or `combo`, the binding as written, the evdev key it
resolves to, and the action. Desktop shortcut config is read only for the
running desktop (GNOME schemas are installed on KDE systems too and would
report bindings nothing listens for); `--all-desktops` overrides.

## Ask the live system, not only the files

Config files can disagree with what is running:

- **KDE**: KWin never re-reads `kglobalshortcutsrc` during a session. Ask
  kglobalaccel directly for the key you care about:
  ```bash
  python3 "$HKB/bind_kde.py" --check KEY_PAUSE
  ```
- **input-remapper**: a preset only acts if it is the device's autoload preset
  (or was started by hand). The audit marks `autoloaded`.
- **hwdb**: a `KEYBOARD_KEY_<scancode>=` rule means the *original* key at that
  scancode no longer exists - not just that the target key is taken. The audit
  lists rewritten scancodes; match them against `probe_keys.py --listen` output.

## Claims no config file shows

Applications grab keys themselves (dictation tools, push-to-talk, games, IDEs).
No scan finds these. Ask the user once - "anything else you use a single key
for?" - and record the answers so future scans respect them:

```bash
python3 "$HKB/bindings_audit.py" --reserve KEY_F9 "leader key for an on-screen macropad"
python3 "$HKB/bindings_audit.py" --reserve KEY_UP "physically broken"
```

Reservations live in `claims.json` in the per-machine reference and are merged
into every later audit and suggestion. Also worth checking by hand when present:
`~/.config/<app>/` files with a `hotkey` / `shortcut` key for any always-running
tray app the user mentions.

## Report

Lead with what matters for the user's question: for "is X free", the claims on
X (or "free" with which sources were checked); for a full audit, the single-key
claims first, since those are what new bindings collide with.
