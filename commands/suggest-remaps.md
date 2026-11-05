---
description: Suggest keyboard shortcuts, macros, and key remappings based on profile and keycodes
---

# Remap & Macro Suggestions

Analyze the user's keyboard profile and keycode scan to suggest useful remappings, shortcuts, and macros.

## Step 1: Load Context

Resolve the plugin's data directory as `$CLAUDE_USER_DATA/keyboard-scanner/` if `CLAUDE_USER_DATA` is set; otherwise `$XDG_DATA_HOME/claude-plugins/keyboard-scanner/` if `XDG_DATA_HOME` is set; otherwise `~/.local/share/claude-plugins/keyboard-scanner/`. Referred to below as `$DATA`.

1. Read keyboard profiles from `$DATA/keyboards/`
2. Read keycode scans from `$DATA/keycodes/`
3. If either is missing, tell the user to run `/keyboard-intake` and/or `/scan-keycodes` first

## Step 2: Identify Underused Keys

Based on the user's profile (especially "unused/annoying keys" and "primary use case"), identify keys that are strong candidates for remapping:

### Commonly underused keys:
- **Insert** — rarely used in modern workflows
- **Scroll Lock** — vestigial, almost never used
- **Pause/Break** — rarely needed
- **Caps Lock** — frequently remapped (to Ctrl, Escape, Hyper, etc.)
- **Num Lock** (on laptops without numpads) — often unnecessary
- **Menu/Context key** — underused on many keyboards
- **Right Ctrl / Right Alt** (depending on user habits)
- **Print Screen** (if user has screenshot tools bound elsewhere)

### Laptop-specific:
- Fn key combinations that duplicate other shortcuts
- Vendor-specific keys (e.g., ThinkPad microphone mute)

## Step 3: Generate Suggestions

Tailor suggestions to the user's **primary use case**:

### For programmers:
- Caps Lock → Escape (vim) or Ctrl (Emacs/general)
- Insert → toggle terminal
- Scroll Lock → build/compile trigger
- Hyper key (Caps Lock) for window management
- Compose key for special characters (→, ≠, ≥, etc.)

### For writers:
- Caps Lock → language/input switch
- Insert → word count macro
- Scroll Lock → distraction-free mode toggle
- Media keys for dictation start/stop

### For general productivity:
- Caps Lock → Hyper key (for a whole new modifier layer)
- Insert → clipboard manager toggle
- Scroll Lock → do-not-disturb toggle
- Menu key → app launcher
- Print Screen → screenshot tool (if not already)

### For all users:
- Key chords for common actions (e.g., Hyper+T → terminal)
- Text expansion triggers
- Window tiling shortcuts

## Step 4: Provide Implementation Instructions

For each suggestion, include:
- **What**: The remapping/shortcut
- **Why**: How it helps the user's workflow
- **How**: The Linux command or tool to implement it

Tools to reference:
- `xmodmap` — simple key remaps (X11)
- `xdotool` — simulate keypresses
- `xbindkeys` — bind keys to commands
- `keyd` — system-level key remapping daemon
- `kmonad` — advanced keyboard configuration
- `xremap` — Wayland-compatible remapper
- `input-remapper` — GUI-based remapper (X11 + Wayland)
- Desktop environment settings (GNOME, KDE shortcut managers)
- `autokey` — text expansion and scripting

## Step 5: Save Output

Save to `$DATA/suggestions/{name-slug}-suggestions.md`:

```markdown
# Remap Suggestions: {Keyboard Name}

## Profile Summary
- Device: ...
- Use case: ...
- Current customizations: ...

## Underused Keys Identified
1. {key} — {reason it's underused}
2. ...

## Recommended Remaps

### High Priority
| Key | Remap To | Benefit | Implementation |
|-----|----------|---------|----------------|
| ... | ...      | ...     | ...            |

### Nice to Have
| Key | Remap To | Benefit | Implementation |
|-----|----------|---------|----------------|
| ... | ...      | ...     | ...            |

## Implementation Guide

### Using {recommended tool}
```
{commands}
```

### Making it persistent
{instructions for making remaps survive reboot}

## Notes
- {any caveats, compatibility notes, etc.}

## Generated
{date}
```

## Step 6: Ask Follow-up

Ask the user:
- "Would you like me to implement any of these remaps now?"
- "Want to refine suggestions for a specific use case?"
- "Should I profile another keyboard?"
