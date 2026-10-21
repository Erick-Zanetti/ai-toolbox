# Changelog

All notable changes to this project. Dates are YYYY-MM-DD.

## Unreleased

### Added
- Reply (`ai-toolbox reply`, palette): writes your answer to the selected
  message from short notes in any language, in the message's language and
  your voice (`context.md`); empty notes suggest three replies. Copies, never
  replaces.
- Tone and alternatives in the result and reply windows: Ctrl+T cycles
  neutral → casual → formal → friendly → direct; Alt+Down lists three other
  versions to pick from.
- History of delivered results (last 50, `[history]` in config.toml, toggle
  in Settings): History in the palette, `ai-toolbox history [--json|--clear]`.
- Dictation: local Whisper speech-to-text (GPU or CPU), a recording pill,
  `ai-toolbox dictate [--then <command>]`, settings for model and language.
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

### Changed
- Settings: every model field is now a list to pick from (provider default
  models, commands, translation, dictation), and so is Codex's reasoning
  effort. The lists come from the Claude CLI aliases, the Codex CLI's model
  cache, the OpenAI-compatible server's `/models` (fetched in the background,
  Settings opens at once) and the Whisper sizes. A command's or translation's
  model list follows its provider; "Provider default" leaves the model unset.
- The daemon logs each action (name and command id, never your text) and any
  crash in a flow with its traceback; SIGUSR1 dumps all thread stacks.

### Fixed
- Choosing something in the palette (Settings, History, a command) sometimes
  did nothing: windows reported their outcome only when Python's garbage
  collector destroyed them. They now report it the moment they close.
- An app that owns the selection but never sends it no longer freezes the
  daemon: reading the selection and the clipboard gives up after 2 s.

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
