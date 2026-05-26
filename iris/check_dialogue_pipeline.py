import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from iris.config.settings import load_settings
from iris.ai.gemma_client import GemmaClient, ChatMessage, _sanitize_visible_reply
from iris.ai.thinking_policy import LlmPurpose, resolve_think
from iris.assistant.dialogue_agent import _DIALOGUE_SYSTEM
USER = "안녕 아이리스"
settings = load_settings()
client = GemmaClient(settings)
think = resolve_think(settings.thinking_mode, LlmPurpose.DIALOGUE_CHAT)
messages = [
    ChatMessage("system", _DIALOGUE_SYSTEM),
    ChatMessage("user", USER),
]
raw = client._chat_ollama(messages, think=think)
cleaned = _sanitize_visible_reply(raw)
print("model:", settings.gemma_model_name)
print("thinking_mode:", settings.thinking_mode, "think:", think)
print("raw len:", len(raw), "|", repr(raw[:250]))
print("cleaned len:", len(cleaned), "|", repr(cleaned[:250]))