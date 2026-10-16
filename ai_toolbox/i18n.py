"""UI strings follow the system language (LANGUAGE / LC_ALL / LC_MESSAGES / LANG).
English is the source; add a table below to support another language."""

from __future__ import annotations

import os

_PT = {
    "Copied.": "Copiado.",
    "Copied: press Ctrl+V to paste.": "Copiado: aperte Ctrl+V para colar.",
    "Search commands": "Buscar comandos",
    "Selected text": "Texto selecionado",
    "No text selected": "Nenhum texto selecionado",
    "Replaces the selection": "Substitui a seleção",
    "Shows the result": "Mostra o resultado",
    "Translate text": "Traduzir texto",
    "Enter run  ·  Esc close": "Enter executar  ·  Esc fechar",
    "{name} failed: {err}": "{name} falhou: {err}",
    "{name}: empty reply.": "{name}: resposta vazia.",
    "{name}: nothing to change.": "{name}: nada a mudar.",
    "{name}: done.": "{name}: pronto.",
    "{name}: select some text first.": "{name}: selecione um texto primeiro.",
    "Error: {err}": "Erro: {err}",
    "No changes.": "Sem mudanças.",
    "Original": "Original",
    "Result": "Resultado",
    "Ctrl+Enter replace": "Ctrl+Enter substituir",
    "Ctrl+Shift+C copy": "Ctrl+Shift+C copiar",
    "Ctrl+R retry": "Ctrl+R refazer",
    "Esc close": "Esc fechar",
    "Translate": "Traduzir",
    "Detect language": "Detectar idioma",
    "Swap (Ctrl+S)": "Inverter (Ctrl+S)",
    "With context": "Com contexto",
    "with context": "com contexto",
    "literal": "literal",
    "Detected: {lang}": "Detectado: {lang}",
    "{n} word": "{n} palavra",
    "{n} words": "{n} palavras",
    "Ctrl+Enter paste into app": "Ctrl+Enter colar no app",
    "Ctrl+S swap": "Ctrl+S inverter",
    "Ctrl+I with context": "Ctrl+I com contexto",
    "Ctrl+P target": "Ctrl+P destino",
    "Esc clear/close": "Esc limpar/fechar",
}

_TABLES = {"pt": _PT}

# Language names the model writes its notes in.
_NAMES = {"en": "English", "pt": "Brazilian Portuguese"}


def _lang() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return value.split(":")[0].split("_")[0].split(".")[0].lower()
    return "en"


LANG = _lang()
_TABLE = _TABLES.get(LANG, {})


def t(message: str, **values) -> str:
    return _TABLE.get(message, message).format(**values)


def language_name() -> str:
    """The system language, in English, for prompts ('reply in ...')."""
    return _NAMES.get(LANG, "English")
