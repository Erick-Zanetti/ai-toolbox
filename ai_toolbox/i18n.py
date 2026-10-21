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
    "{name} failed: {err}": "{name} falhou: {err}",
    "{name}: empty reply.": "{name}: resposta vazia.",
    "{name}: nothing to change.": "{name}: nada a mudar.",
    "{name}: done.": "{name}: pronto.",
    "{name}: select some text first.": "{name}: selecione um texto primeiro.",
    "Error: {err}": "Erro: {err}",
    "No changes.": "Sem mudanças.",
    "Original": "Original",
    "Settings": "Configurações",
    "Personal dictionary": "Dicionário pessoal",
    "Product names, acronyms and jargon that commands and translations must never change.": "Nomes de produtos, siglas e jargões que comandos e traduções nunca devem mudar.",
    "Terms (comma separated)": "Termos (separados por vírgula)",
    "Replace": "Substituir",
    "Paste": "Colar",
    "Copy": "Copiar",
    "Thinking…": "Pensando…",
    "retry": "refazer",
    "stop": "parar",
    "cancel": "cancelar",
    "Listening…": "Ouvindo…",
    "Setting up dictation (one time, ~1 GB)…": "Preparando o ditado (só na primeira vez, ~1 GB)…",
    "Loading the speech model…": "Carregando o modelo de voz…",
    "Transcribing…": "Transcrevendo…",
    "Applying {name}…": "Aplicando {name}…",
    "Dictation failed: {err}": "Ditado falhou: {err}",
    "Nothing heard.": "Nada foi ouvido.",
    "Dictation": "Ditado",
    "Local Whisper speech-to-text. The first use downloads the model.": "Voz para texto local com Whisper. O primeiro uso baixa o modelo.",
    "Device": "Dispositivo",
    "Automatic (GPU when available)": "Automático (GPU quando houver)",
    "GPU model": "Modelo na GPU",
    "CPU model": "Modelo na CPU",
    "Language (empty = detect)": "Idioma (vazio = detectar)",
    "Paste as spoken": "Colar como foi falado",
    "After transcribing": "Depois de transcrever",
    "ask": "pedir",
    "Ask for a change… e.g. more formal, as bullet points": "Pedir uma mudança… ex.: mais formal, em tópicos",
    "close": "fechar",
    "swap": "inverter",
    "target": "destino",
    "clear/close": "limpar/fechar",
    "navigate": "navegar",
    "run": "executar",
    "Claude Code CLI · Claude subscription": "Claude Code CLI · assinatura do Claude",
    "Codex CLI · ChatGPT subscription": "Codex CLI · assinatura do ChatGPT",
    "OpenAI-compatible server": "Servidor compatível com OpenAI",
    "Commands, notifications, models": "Comandos, notificações, modelos",
    "General": "Geral",
    "Commands": "Comandos",
    "Context": "Contexto",
    "Behavior": "Comportamento",
    "Notifications": "Notificações",
    "All": "Todas",
    "Errors only": "Só erros",
    "Off": "Desligadas",
    "Progress and results of commands that replace text directly": "Progresso e resultado dos comandos que substituem o texto direto",
    "Copy when nothing is highlighted": "Copiar quando nada estiver selecionado",
    "Sends Ctrl+C to the app (never to terminals)": "Manda Ctrl+C para o app (nunca para terminais)",
    "AI accounts": "Contas de IA",
    "claude and codex use your logged-in CLIs; openai is any OpenAI-compatible server such as Ollama.": "claude e codex usam seus CLIs logados; openai é qualquer servidor compatível com OpenAI, como o Ollama.",
    "Default provider": "Provedor padrão",
    "Default model": "Modelo padrão",
    "Reasoning effort": "Esforço de raciocínio",
    "Server URL": "URL do servidor",
    "API key variable (optional)": "Variável da API key (opcional)",
    "Add local models (Ollama)": "Adicionar modelos locais (Ollama)",
    "Added. Reopen settings to edit it.": "Adicionado. Reabra as configurações para editar.",
    "Replaces directly": "Substitui direto",
    "Shows a window": "Mostra janela",
    "Name": "Nome",
    "Show a window": "Mostrar janela",
    "Replace directly": "Substituir direto",
    "Provider": "Provedor",
    "Default": "Padrão",
    "Model": "Modelo",
    "Provider default": "Padrão do provedor",
    "Model default": "Padrão do modelo",
    "Icon name": "Nome do ícone",
    "Prompt  ·  {selection} {clipboard} {context}": "Prompt  ·  {selection} {clipboard} {context}",
    "Delete command": "Excluir comando",
    "Each command runs a prompt on the selected text.": "Cada comando roda um prompt sobre o texto selecionado.",
    "New command": "Novo comando",
    "Languages": "Idiomas",
    "Auto target: text in one language of the pair goes to the other.": "Destino automático: texto em um idioma do par vai para o outro.",
    "Language A": "Idioma A",
    "Language B": "Idioma B",
    "More languages (comma separated)": "Mais idiomas (separados por vírgula)",
    "Literal translation": "Tradução literal",
    "Translation with context": "Tradução com contexto",
    "About you": "Sobre você",
    "Used by translation with context and by commands with {context}: who you are, who you write to, the tone you want.": "Usado pela tradução com contexto e pelos comandos com {context}: quem você é, para quem escreve, o tom que quer.",
    "Config error: {err}": "Erro na config: {err}",
    "Result": "Resultado",
    "Translate": "Traduzir",
    "Detect language": "Detectar idioma",
    "Swap (Ctrl+S)": "Inverter (Ctrl+S)",
    "With context": "Com contexto",
    "with context": "com contexto",
    "literal": "literal",
    "Detected: {lang}": "Detectado: {lang}",
    "{n} word": "{n} palavra",
    "{n} words": "{n} palavras",
    "tone": "tom",
    "alternatives": "alternativas",
    "neutral": "neutro",
    "casual": "casual",
    "formal": "formal",
    "friendly": "amigável",
    "direct": "direto",
    "No alternatives.": "Nenhuma alternativa.",
    "Reply": "Responder",
    "Write a reply to the selected message": "Escrever uma resposta para a mensagem selecionada",
    "Received message": "Mensagem recebida",
    "Your notes, in any language… empty: three suggestions": "Suas anotações, em qualquer idioma… vazio: três sugestões",
    "Paste the message you received first.": "Cole primeiro a mensagem que você recebeu.",
    "write": "escrever",
    "copy": "copiar",
    "History": "Histórico",
    "Recent results, copy one again": "Resultados recentes, copie de novo",
    "Search history": "Buscar no histórico",
    "Clear history": "Limpar histórico",
    "Clear history?": "Limpar o histórico?",
    "Every saved result is deleted. This cannot be undone.": "Todos os resultados salvos são apagados. Não dá para desfazer.",
    "Cancel": "Cancelar",
    "Clear": "Limpar",
    "Nothing here yet: results you replace, paste or copy show up here.": "Nada aqui ainda: os resultados que você substitui, cola ou copia aparecem aqui.",
    "Keep a history": "Manter histórico",
    "Recent results, under History in the palette. Stays on this computer.": "Resultados recentes, em Histórico na paleta. Fica só neste computador.",
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
    text = _TABLE.get(message, message)
    return text.format(**values) if values else text


def language_name() -> str:
    """The system language, in English, for prompts ('reply in ...')."""
    return _NAMES.get(LANG, "English")
