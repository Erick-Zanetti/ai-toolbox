"""Load ~/.config/ai-toolbox: config.toml, context.md and commands/*.toml."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ai-toolbox"
# Defaults shipped next to the code (checkout) or in /usr/share (packages).
EXAMPLES_DIRS = (
    Path(__file__).resolve().parent.parent / "examples",
    Path("/usr/share/ai-toolbox/examples"),
    Path("/usr/local/share/ai-toolbox/examples"),
)

OUTPUTS = ("replace", "window")
KINDS = ("claude", "codex", "openai")
NOTIFICATIONS = ("all", "errors", "off")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Model:
    """Which account (provider) and model answers a request."""

    provider: str
    model: str
    reasoning: str | None = None
    kind: str = ""  # claude | codex | openai; defaults to the provider name
    base_url: str | None = None  # openai: e.g. http://localhost:11434/v1 (Ollama)
    api_key_env: str | None = None  # openai: env var holding the key, if any

    @property
    def type(self) -> str:
        return self.kind or self.provider


@dataclass(frozen=True)
class Command:
    id: str
    name: str
    icon: str
    prompt: str
    output: str
    model: Model
    diff: bool = True  # highlight changes in the result window


@dataclass(frozen=True)
class Translate:
    languages: tuple[str, ...]
    pair: tuple[str, str]
    literal: Model
    contextual: Model


@dataclass(frozen=True)
class Config:
    default: Model
    translate: Translate
    context: str
    terminal_classes: tuple[str, ...]
    copy_fallback: bool = False
    notifications: str = "all"  # all | errors | off
    glossary: tuple[str, ...] = ()  # terms the AI must never change
    commands: dict[str, Command] = field(default_factory=dict)


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path}: {err}") from err


def _model(raw: dict, fallback: Model, providers: dict) -> Model:
    provider = raw.get("provider", fallback.provider)
    if provider not in providers:
        raise ConfigError(f"unknown provider '{provider}' (known: {', '.join(providers)})")
    defaults = providers[provider]
    same_provider = provider == fallback.provider
    model = raw.get("model") or (fallback.model if same_provider else "") or defaults.get("model")
    if not model:
        raise ConfigError(f"provider '{provider}' needs a model")
    kind = defaults.get("type", provider)
    if kind not in KINDS:
        raise ConfigError(f"provider '{provider}': type must be one of {KINDS}")
    if kind == "openai" and not defaults.get("base_url"):
        raise ConfigError(f"provider '{provider}': type 'openai' needs base_url")
    return Model(
        provider=provider,
        model=model,
        reasoning=raw.get("reasoning", defaults.get("reasoning")),
        kind=kind if kind != provider else "",
        base_url=defaults.get("base_url"),
        api_key_env=defaults.get("api_key_env"),
    )


def _command(path: Path, default: Model, providers: dict) -> Command:
    raw = _read_toml(path)
    if "prompt" not in raw:
        raise ConfigError(f"{path}: missing 'prompt'")
    output = raw.get("output", "window")
    if output not in OUTPUTS:
        raise ConfigError(f"{path}: output must be one of {OUTPUTS}")
    return Command(
        id=path.stem,
        name=raw.get("name", path.stem),
        icon=raw.get("icon", "document-edit-symbolic"),
        prompt=raw["prompt"],
        output=output,
        model=_model(raw, default, providers),
        diff=bool(raw.get("diff", True)),
    )


def ensure_user_config(config_dir: Path = CONFIG_DIR) -> None:
    """First run: copy the shipped examples so the user has files to edit."""
    if (config_dir / "config.toml").exists():
        return
    source = next((d for d in EXAMPLES_DIRS if (d / "config.toml").exists()), None)
    if source is None:
        raise ConfigError(f"no {config_dir / 'config.toml'} and no shipped examples found")
    shutil.copytree(source, config_dir, dirs_exist_ok=True)


def load(config_dir: Path = CONFIG_DIR) -> Config:
    if config_dir == CONFIG_DIR:
        ensure_user_config(config_dir)
    raw = _read_toml(config_dir / "config.toml")
    providers = raw.get("providers", {})
    if not providers:
        raise ConfigError("config.toml: no [providers]")

    default_name = raw.get("default_provider", next(iter(providers)))
    default = _model({"provider": default_name}, Model(default_name, ""), providers)

    notifications = raw.get("notifications", "all")
    if notifications not in NOTIFICATIONS:
        raise ConfigError(f"notifications must be one of {NOTIFICATIONS}")

    tr = raw.get("translate", {})
    pair = tuple(tr.get("pair", ("English", "Portuguese (Brazil)")))
    if len(pair) != 2:
        raise ConfigError("translate.pair needs exactly two languages")
    languages = tuple(dict.fromkeys([*pair, *tr.get("languages", [])]))
    translate = Translate(
        languages=languages,
        pair=pair,
        literal=_model(tr.get("literal", {}), default, providers),
        contextual=_model(tr.get("contextual", {}), default, providers),
    )

    context_file = config_dir / "context.md"
    context = context_file.read_text() if context_file.exists() else ""

    commands_dir = config_dir / "commands"
    commands = {
        cmd.id: cmd
        for cmd in (_command(p, default, providers) for p in sorted(commands_dir.glob("*.toml")))
    }

    return Config(
        default=default,
        translate=translate,
        context=context,
        terminal_classes=tuple(raw.get("terminal_classes", ())),
        copy_fallback=bool(raw.get("copy_fallback", False)),
        notifications=notifications,
        glossary=tuple(str(term) for term in raw.get("glossary", ()) if str(term).strip()),
        commands=commands,
    )
