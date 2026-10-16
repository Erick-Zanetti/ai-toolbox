<p align="center">
  <img src="data/dev.aitoolbox.AiToolbox.svg" width="96" alt="">
</p>

<h1 align="center">AI Toolbox</h1>

<p align="center">Raycast-style AI text commands and translator for Wayland desktops.<br>
Select text anywhere, press a shortcut, get it fixed, rewritten or translated.</p>

- **Commands.** Fix spelling, improve writing, change tone: each one is a small
  TOML file with a prompt. `output = "replace"` swaps the selection in place,
  no window; `output = "window"` shows the result first, streaming, with the
  changed words highlighted. Ctrl+Enter puts it back over the selection.
- **Command palette.** One shortcut lists every command; type to filter, Enter to run.
- **Translator.** Source on top, translation below, live as you type, language
  detected on the fly. Literal by default; **With context** (Ctrl+I) adapts the
  translation to who you are and who you write to (`context.md`), and tells you
  when it changed something on purpose.
- **Your own AI accounts.** Uses the Claude and ChatGPT subscriptions you
  already have through their official CLIs (no API keys), or local models
  through any OpenAI-compatible endpoint (Ollama, LM Studio, llama.cpp).
- **Fits your desktop.** GTK 4 + libadwaita: follows your light/dark mode,
  accent and theme colors. UI in your system language (English, Portuguese).

## Requirements

- A Wayland session, `wl-clipboard`, `libnotify`
- GTK 4, libadwaita and PyGObject from your distro (Python ≥ 3.11)
- At least one model provider:
  - [`claude`](https://docs.claude.com/en/docs/claude-code) logged in with a Claude subscription
  - [`codex`](https://github.com/openai/codex) logged in with a ChatGPT subscription
  - [Ollama](https://ollama.com) or another OpenAI-compatible server

### Desktop support

| Desktop | Window tracking | Paste back |
|---|---|---|
| Hyprland | native IPC | native (no extra tools) |
| Sway, niri | native IPC | `wtype` or `ydotool` |
| KDE, GNOME, others | — | `ydotool` (focus returns to the app on its own) |

Without a way to send keys the result stays on the clipboard and a
notification tells you to press Ctrl+V.

Text comes from the primary selection: just highlight it. For apps without
one, `copy_fallback = true` sends them a Ctrl+C instead (never to terminals).

## Install

Arch (AUR-style package in [`packaging/arch`](packaging/arch/PKGBUILD)):

```sh
cd packaging/arch && makepkg -si
```

From a checkout:

```sh
ln -s "$PWD/bin/ai-toolbox" ~/.local/bin/ai-toolbox
```

The first run copies the example config to `~/.config/ai-toolbox/`.

### Shortcuts

Bind these in your compositor:

| Shortcut (suggested) | Command |
|---|---|
| Super+Alt+C | `ai-toolbox run fix-spelling` |
| Super+Alt+T | `ai-toolbox translate` |
| Super+Alt+Space | `ai-toolbox` (palette) |

Hyprland (Lua config):

```lua
hl.window_rule({ match = { class = "dev.aitoolbox.AiToolbox" }, float = true, center = true })
```

Sway: `for_window [app_id="dev.aitoolbox.AiToolbox"] floating enable`.
niri: a `window-rule` matching `app-id="dev.aitoolbox.AiToolbox"` with `open-floating true`.

## Usage

```
ai-toolbox                    command palette
ai-toolbox run <command>      run on the selection (output from the command file)
ai-toolbox window <command>   same, always showing the result window
ai-toolbox translate          translator, prefilled with the selection (--empty to skip)
ai-toolbox list               list commands
```

| Window | Keys |
|---|---|
| Result | Ctrl+Enter replace · Ctrl+Shift+C copy · Ctrl+R retry · Esc close |
| Translator | Ctrl+Enter paste into app · Ctrl+Shift+C copy · Ctrl+S swap · Ctrl+I with context · Ctrl+P / Ctrl+Shift+P target / source · Esc clear, then close |

## Configuration

`~/.config/ai-toolbox/config.toml` holds the providers, the translator
languages and models; see [`examples/config.toml`](examples/config.toml).

### Adding a command

One file per command in `~/.config/ai-toolbox/commands/<id>.toml`:

```toml
name = "Make it friendlier"
icon = "face-smile-symbolic"   # optional, any symbolic icon name
output = "window"              # "replace" or "window"
provider = "claude"            # optional: a provider from config.toml
model = "haiku"                # optional
prompt = """
Rewrite the text in a warmer, friendlier tone. Keep the meaning and language.

<text>
{selection}
</text>
"""
```

Placeholders: `{selection}`, `{clipboard}`, `{context}` (the contents of
`context.md`). Without `{selection}` the text is appended to the prompt.

## Development

```sh
uv run --no-project --with pytest python -m pytest
```

Adding a UI language: add a table to [`ai_toolbox/i18n.py`](ai_toolbox/i18n.py).

## License

[MIT](LICENSE)
