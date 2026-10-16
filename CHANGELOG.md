# Changelog

All notable changes to this project. Dates are YYYY-MM-DD.

## Unreleased

### Added
- Daemon mode: `ai-toolbox daemon` (and `ai-toolbox.service`) keeps one
  instance running; later calls reach it through a gdbus fast path, so
  windows open almost instantly.
- "Ask for a change" field in the result window (Ctrl+L): free instructions
  like "more formal" or "as bullet points" rework the current result.
- Personal dictionary (`glossary`): terms no command or translation changes.
- Commands: Make it professional, Make it casual, Shorten, Explain.
- `{language}` placeholder and per-command `diff = false`.
- Pasting on GNOME and KDE through the RemoteDesktop portal (asks once).
- CI: lint and tests on GitHub Actions.
- AUR-ready `ai-toolbox-git` package (PKGBUILD + .SRCINFO, builds clean).

## 0.1.0 — 2026-10-15

First release.

- AI commands on the selected text through the Claude Code / Codex CLIs
  (your subscriptions) or OpenAI-compatible servers (Ollama, LM Studio).
- Result window: original and result side by side with a word diff, both
  editable; Ctrl+R reruns on the result; Ctrl+Enter replaces the selection.
- Commands can instead replace the selection directly, with notifications.
- Command palette, translator (literal or adapted to your `context.md`),
  settings window (commands, notifications, models, languages, context).
- Follows the system theme (libadwaita) and language (English, Portuguese).
- Hyprland, Sway and niri window tracking; wtype / ydotool paste fallback.
- Arch PKGBUILD, desktop entry and icon.
