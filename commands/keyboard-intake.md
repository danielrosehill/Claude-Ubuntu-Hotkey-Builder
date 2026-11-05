---
description: Profile the user's keyboard setup through an interactive questionnaire
---

# Keyboard Intake

You are conducting an intake interview to profile the user's keyboard setup. Ask questions one at a time and wait for responses. Be conversational but efficient.

## Questions to ask (in order):

### 1. Device Type
Ask: "What type of computer are you using? (laptop / desktop / both)"

### 2. If laptop:
- "What's the laptop make and model?" (e.g., ThinkPad T14s Gen 3, MacBook Pro 16")
- "Are you using the built-in keyboard, or do you also have an external keyboard connected?"

### 3. If desktop or external keyboard:
- "What keyboard are you using?" (make/model if known, or describe it — full-size, TKL, 60%, split, etc.)
- "What switch type?" (membrane, mechanical — if mechanical, what switches?)
- "Does it have a number pad?"
- "Any special keys or extra buttons?" (media keys, macro keys, rotary knobs, etc.)

### 4. For all setups:
- "What keyboard layout are you using?" (US QWERTY, UK, Dvorak, Colemak, ISO vs ANSI, etc.)
- "Do you have any existing key remaps, custom shortcuts, or macro software set up?"
- "Are there any keys you never use or find annoying?" (e.g., Caps Lock, Insert, Scroll Lock)
- "What's your primary use case?" (programming, writing, gaming, general productivity, etc.)
- "Any accessibility needs or preferences?" (one-handed typing, RSI concerns, etc.)

### 5. Multiple keyboards:
If the user has multiple input devices, ask: "Which keyboard(s) would you like to profile? We can do multiple."

## After gathering responses:

Resolve the plugin's data directory as `$CLAUDE_USER_DATA/keyboard-scanner/` if `CLAUDE_USER_DATA` is set; otherwise `$XDG_DATA_HOME/claude-plugins/keyboard-scanner/` if `XDG_DATA_HOME` is set; otherwise `~/.local/share/claude-plugins/keyboard-scanner/`. Create it if missing. Referred to below as `$DATA`.

1. Create a keyboard profile in `$DATA/keyboards/{name-slug}.md` with all gathered information structured as:

```markdown
# Keyboard Profile: {Name}

## Device
- **Type**: laptop / desktop / external
- **Make/Model**: ...
- **Laptop Model** (if applicable): ...
- **Form Factor**: full-size / TKL / 75% / 65% / 60% / split / other
- **Switch Type**: membrane / mechanical ({switch name}) / other
- **Number Pad**: yes / no
- **Layout**: US QWERTY / etc.
- **Connection**: built-in / USB / Bluetooth / 2.4GHz wireless

## Special Keys
- Media keys: yes/no (list)
- Macro keys: yes/no (list)
- Other: ...

## Current Customizations
- Existing remaps: ...
- Custom shortcuts: ...
- Macro software: ...

## User Preferences
- Primary use case: ...
- Unused/annoying keys: ...
- Accessibility needs: ...

## Scan Date
{today's date}
```

2. Also save a formatted profile report to `$DATA/profiles/{name-slug}-profile.md`

3. Let the user know they can now run `/scan-keycodes` to map all available keycodes, or `/intake` again to profile another keyboard.
