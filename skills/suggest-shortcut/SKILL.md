---
name: suggest-shortcut
description: Suggest non-conflicting single keys for a new shortcut or macro on Ubuntu, ranked for the purpose (type text, run a command, or remap to another key), with the binding route each needs (desktop shortcut, interceptor, or two-stage) and caveats such as keysym collisions, keypad keys KWin ignores, and multi-layout text injection. Use for "find me a free key for...", "which key can I use for a macro", "suggest a hotkey that doesn't conflict", "what spare keys does this laptop have".
---

# Suggest free keys

```bash
HKB="${CLAUDE_PLUGIN_ROOT:-$HOME/.local/share/hotkey-builder}/scripts"
[ -f "$HKB/env_check.py" ] || git clone -q https://github.com/danielrosehill/Claude-Ubuntu-Hotkey-Builder "$HOME/.local/share/hotkey-builder"
```

## 0. Reuse the reference

```bash
python3 "$HKB/reference.py" status
```

If `environment.json` is missing or older than the last system change the user
mentions, run `check-environment` first; the suggestions read layouts from it.
Physically confirmed keys from earlier `--listen` runs are reused - do not ask
the user to press keys they already confirmed.

## 1. Rank

```bash
python3 "$HKB/suggest_keys.py" --purpose text --save     # or: command | key
```

Output sections:

- **Free single keys** - score, `pressed` (physically confirmed) or `declared`,
  the routes that can work, why it is a candidate, caveats.
- **Already taken** - excluded, with who owns them.
- **Free two-stage targets** - F14-F18 style keys nothing claims and no
  keyboard physically has; remap a real key onto one with input-remapper, bind
  that on the desktop.
- **Scancodes rewritten by hwdb** - keys that no longer exist under their old name.

## 2. Narrow it with the user

Present three or four options, not the whole list. For each: the key as printed
on the keyboard (ask if unsure which physical key emits it), the route, the one
caveat that matters. Fit them to the purpose:

- **Text injection**: the key must not type anything itself in the focused app.
  Desktop and interceptor routes both swallow it; a key left unbound and only
  read by a daemon does not.
- **Several keyboard layouts + text**: prefer keys with the `desktop` route, or
  two-stage, so `hkb-type` can pin the Latin layout. A plain interceptor macro
  types through whatever layout is active.
- **Keys the user rarely notices**: Pause, Scroll Lock, Menu, vendor keys are
  usually better than an F-key that some app uses.

## 3. Confirm physically before binding

Unconfirmed candidates must be pressed once:

```bash
python3 "$HKB/probe_keys.py" --listen --seconds 30 --save
```

Ask the user to press the shortlisted keys. A shortlisted key that prints
nothing does not exist on this keyboard (or is grabbed elsewhere) - drop it.
Then hand over to `create-shortcut`.
