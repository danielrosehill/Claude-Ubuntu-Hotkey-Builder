---
name: create-shortcut
description: End to end - create a working, non-conflicting keyboard shortcut or macro on Ubuntu, such as one key that types "claude" and presses Enter, a key that runs a command, or a key remapped to another. Detects the environment, reuses the per-machine reference from earlier scans, audits existing bindings, suggests free keys, confirms the key physically, implements it by the right route (KDE kglobalaccel D-Bus, GNOME gsettings, input-remapper, or two-stage), verifies it with a real key press, and logs it with an undo command. Use for "make a hotkey that types X", "bind a key to run Y", "text injection shortcut", "single-key macro", "talkie / push-to-talk key".
---

# Create a shortcut

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
```

Follow the steps in order. Each one reuses saved results when they are fresh,
so on a machine that has been scanned before most steps are a single read.

## 1. Pin down the request

Get, in one exchange if anything is missing:

- **what it does**: type text (and whether to press Enter after), run a
  command, or emit another key / chord;
- **which keyboard** if there is more than one (laptop, external, macropad, pedal);
- **any key the user already has in mind**, and anything they use single keys
  for that no config would show (dictation, push-to-talk, a launcher).

Record the last answer with `bindings_audit.py --reserve` so it is never asked again.

## 2. Environment and reference

```bash
python3 "$HKB/reference.py" status
python3 "$HKB/env_check.py" --save          # if missing or stale
python3 "$HKB/usb_inventory.py" --save      # if missing, or a device was added
```

Fix blockers through `check-environment` (ydotoold not running, user not in
`input`). For text injection install the injector wrapper once:

```bash
install -Dm755 "$HKB/inject_text.py" "$HOME/.local/bin/hkb-type"
"$HOME/.local/bin/hkb-type" --dry-run --enter "claude"     # shows backend + commands, types nothing
```

## 3. Candidates

```bash
python3 "$HKB/bindings_audit.py" --save
python3 "$HKB/suggest_keys.py" --purpose text --save        # text | command | key
```

Shortlist three or four with the user (see `suggest-shortcut`), then confirm the
shortlist physically unless already confirmed:

```bash
python3 "$HKB/probe_keys.py" --listen --seconds 30 --save
```

## 4. Implement by route

Pick the first route the chosen key supports, in this order of preference.

**A. Desktop shortcut (KDE)** - key has the `desktop` route:

```bash
python3 "$HKB/bind_kde.py" --check KEY_PAUSE
python3 "$HKB/bind_kde.py" --verify KEY_PAUSE --seconds 20   # user presses the key; proves KWin fires on it
python3 "$HKB/bind_kde.py" --bind KEY_PAUSE --name "Type claude" \
        --command "$HOME/.local/bin/hkb-type --enter claude"
```

Use the absolute path in `--command`: launchers do not get the shell's PATH.
Undo: `bind_kde.py --unbind "Type claude"`.

**B. Desktop shortcut (GNOME)**:

```bash
python3 "$HKB/bind_gnome.py" --bind KEY_PAUSE --name "Type claude" \
        --command "$HOME/.local/bin/hkb-type --enter claude"
```

Undo: `bind_gnome.py --unbind "Type claude"`.

**C. Interceptor macro** - any key, any desktop; text only when a single Latin
layout is configured:

```bash
python3 "$HKB/bind_input_remapper.py" --device "<name from --list-devices>" \
        --key KEY_KPSLASH --text "claude" --enter
```

Undo: `bind_input_remapper.py --device "<name>" --unbind KEY_KPSLASH`.

**D. Two-stage** - keypad keys on KDE, keys without a keysym, or text with
several layouts on an interceptor-only key. Remap the physical key onto a free
target from `suggest_keys.py` (F14-F18), then bind the target as in A/B:

```bash
python3 "$HKB/bind_input_remapper.py" --device "<name>" --key KEY_KPSLASH --to-key KEY_F14
python3 "$HKB/bind_kde.py" --bind KEY_F14 --name "Type claude" \
        --command "$HOME/.local/bin/hkb-type --enter claude"
```

The target key does not exist physically, so `--verify` on it means pressing
the *physical* key after the remap is applied.

Never bind a key that `--check` or the audit shows taken unless the user
explicitly agrees to replace that binding.

## 5. Verify with a real press

Synthetic presses (ydotool) are not evidence on KDE - KWin did not fire
shortcuts for them in testing. Ask the user to put the cursor somewhere
harmless (an empty editor, a terminal prompt they can clear) and press the key.
Report exactly what they saw. If the text came out in the wrong script, the
layout pin did not take: pass `--layout N` to `hkb-type` with the index of the
Latin layout.

## 6. Log it

```bash
python3 "$HKB/reference.py" log --key KEY_PAUSE --route kde-dbus \
        --action "types: claude + Enter" --undo "bind_kde.py --unbind 'Type claude'" \
        --verified "physical press $(date +%F)"
```

This updates `shortcuts.json` and re-renders the reference README, so the next
session knows the key is taken and how to remove it.

## Facts this relies on

`references/routes.md` - why KDE bindings go through D-Bus and need
`kbuildsycoca6` first, why KWin ignores keypad keys, why wtype fails on
KWin/Mutter, why ydotool needs the layout pin, keysym traps (F13 = KEY_CONFIG,
F19/F24 invisible, F20-F23 pre-bound), and input-remapper macro limits.
