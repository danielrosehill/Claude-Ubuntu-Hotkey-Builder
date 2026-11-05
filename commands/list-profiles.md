---
description: List all keyboard profiles and their scan status
---

# List Keyboard Profiles

Check the current state of all keyboard profiles in this workspace.

## Steps:

Resolve the plugin's data directory as `$CLAUDE_USER_DATA/keyboard-scanner/` if `CLAUDE_USER_DATA` is set; otherwise `$XDG_DATA_HOME/claude-plugins/keyboard-scanner/` if `XDG_DATA_HOME` is set; otherwise `~/.local/share/claude-plugins/keyboard-scanner/`. Referred to below as `$DATA`.

1. List all files in `$DATA/keyboards/` — these are the intake profiles
2. List all files in `$DATA/keycodes/` — these are the keycode scans
3. List all files in `$DATA/suggestions/` — these are the remap suggestions

## Output format:

For each keyboard profile found, show:

```
## Keyboard Profiles

| Keyboard | Profile | Keycodes Scanned | Suggestions Generated |
|----------|---------|-------------------|-----------------------|
| {name}   | yes     | yes/no            | yes/no                |
```

Then suggest next steps:
- If no profiles exist: "Run `/intake` to profile your first keyboard"
- If profiles exist but no scans: "Run `/scan-keycodes` to map keycodes"
- If scans exist but no suggestions: "Run `/suggest-remaps` for remap ideas"
- If everything is complete: "All keyboards profiled! Run `/intake` to add another, or update existing profiles."
