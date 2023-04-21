# promptbuilder/core/token_counter.py

from typing import Literal, Union, List, Dict, Any, Optional
from loguru import logger
from google.api_core import exceptions as gexc

# ——————————————————————————————————————————————
# 1) OpenAI / tiktoken implementation
# ——————————————————————————————————————————————
try:
    import tiktoken
    import tiktoken_ext.openai_public  # ensure cl100k_base & friends are registered
    TIKTOKEN_AVAILABLE = True
    logger.info("tiktoken loaded")
except ImportError:
    tiktoken = None  # type: ignore
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken unavailable; OpenAI counts will be estimated")

class OpenAICounter:
    def __init__(self, model_name: str, fallback: str = "cl100k_base"):
        self.model = model_name
        self.fallback = fallback
        self._cache: Dict[str, Any] = {}

    def _get_encoder(self, name: str):
        if not TIKTOKEN_AVAILABLE:
            return None
        if name in self._cache:
            return self._cache[name]

        enc = None
        try:  # model nick-name?
            enc = tiktoken.encoding_for_model(name)
        except KeyError:
            try:  # maybe caller passed a BPE name
                enc = tiktoken.get_encoding(name)
            except Exception:
                logger.warning(f"{name!r} not recognised, using {self.fallback!r}")
                enc = tiktoken.get_encoding(self.fallback)

        self._cache[name] = enc
        return enc

    def count(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("OpenAI counter expects a single string")
        enc = self._get_encoder(self.model)
        if enc:
            return len(enc.encode(text))
        return max(1, len(text) // 4)  # heuristic


# ——————————————————————————————————————————————
# 2) Gemini / google.generativeai implementation
# ——————————————————————————————————————————————
class GeminiCounter:
    def __init__(self, model_name: str = "gemini-2.5-pro-preview-03-25"):
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("Install google-generativeai for Gemini counting")
        self.model = genai.GenerativeModel(model_name)

    def count(self, content):
        try:
            usage = self.model.count_tokens(content)
            return usage.total_tokens
        except (gexc.GoogleAPICallError, gexc.PermissionDenied) as e:
            logger.warning(f"Gemini count failed ({e}); using heuristic")
            flat = str(content) if not isinstance(content, str) else content
            return max(1, len(flat) // 4)


# ——————————————————————————————————————————————
# 3) Unified wrapper
# ——————————————————————————————————————————————
class UnifiedTokenCounter:
    def __init__(self, backend: Literal["openai", "gemini"], model_name: str, **kwargs):
        if backend == "openai":
            self._impl = OpenAICounter(model_name, fallback=kwargs.pop("fallback", "cl100k_base"))
        elif backend == "gemini":
            self._impl = GeminiCounter(model_name)
        else:
            raise ValueError(f"unknown backend {backend!r}")

    def count(self, content: Union[str, List[Any]]) -> int:
        """
        Count tokens using the selected backend.
        - For OpenAI: content must be a string.
        - For Gemini: content can be string, chat history, or multimodal list.
        """
        return self._impl.count(content)
