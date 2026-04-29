import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Groq endpoint that mirrors the OpenAI Chat Completions API ────────
_GROQ_BASE_URL = 'https://api.groq.com/openai/v1'


class LLMClient:
    """
    Reusable Groq LLM client.

    All methods return a string on success or None on any failure.
    Callers must always handle the None case with a deterministic
    fallback so the system keeps running without the LLM.
    """

    def __init__(self) -> None:
        self._client = None   # lazy — created on first use

    # ─────────────────────────────────────────────────────────────────
    #  INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _get_client(self):
        """
        Lazy-initialise and cache the OpenAI client pointed at Groq.
        Returns None if the API key is missing or the SDK is not
        installed.
        """
        if self._client is not None:
            return self._client

        api_key = getattr(settings, 'GROQ_API_KEY', '').strip()
        if not api_key:
            logger.warning(
                'LLMClient: GROQ_API_KEY is not set. '
                'All LLM calls will return None (fallback mode).'
            )
            return None

        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key  = api_key,
                base_url = _GROQ_BASE_URL,
                timeout  = getattr(settings, 'GROQ_TIMEOUT', 20),
            )
        except ImportError:
            logger.error(
                'LLMClient: "openai" package is not installed. '
                'Run: pip install openai'
            )
        except Exception as exc:
            logger.error(f'LLMClient: client init failed — {exc}')

        return self._client

    # ─────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ─────────────────────────────────────────────────────────────────

    def chat(
        self,
        system:     str,
        user:       str,
        max_tokens: int   = 350,
        temperature: float = 0.65,
    ) -> Optional[str]:
        """
        Send a two-message chat request (system + user) to the LLM.

        Args:
            system:      System-role instructions for the model.
            user:        The user-role prompt / data payload.
            max_tokens:  Maximum tokens in the completion (default 350).
            temperature: Sampling temperature — lower is more focused
                         (default 0.65 balances creativity and accuracy).

        Returns:
            The stripped completion text, or None on any error.
        """
        client = self._get_client()
        if client is None:
            return None

        model = getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-120b')

        try:
            response = client.chat.completions.create(
                model       = model,
                max_tokens  = max_tokens,
                temperature = temperature,
                messages    = [
                    {'role': 'system', 'content': system},
                    {'role': 'user',   'content': user},
                ],
            )
            text = response.choices[0].message.content
            return text.strip() if text else None

        except Exception as exc:
            logger.warning(f'LLMClient.chat failed — {exc}')
            return None