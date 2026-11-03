"""Pluggable local-LLM backends for email correction.

The app never calls a model directly — it goes through a backend with a single
`correct()` method. Default is Ollama over localhost HTTP (stdlib urllib, no
extra dependency). The llama-cpp-python backend runs a GGUF model in-process
(optional dependency — imported lazily so the app runs without it installed).

Correction is deliberately conservative: fix language, keep every fact, invent
nothing — this is a job application, not a creative-writing exercise.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.models import LLMBackend as LLMBackendType
from app.models import Settings


@dataclass
class LLMResult:
    text: str
    ok: bool
    error: str = ""


def _instruction(language: str) -> str:
    if language == "fr":
        return (
            "Tu es un correcteur professionnel. Corrige l'orthographe, la grammaire, "
            "la ponctuation et le registre (vouvoiement professionnel soutenu) du "
            "courriel. Ne change aucun fait, n'invente rien, ne supprime aucune "
            "information, n'ajoute aucun commentaire de ta part. Conserve les sauts "
            "de ligne. Réponds uniquement avec le courriel corrigé."
        )
    return (
        "You are a professional proofreader. Fix the spelling, grammar, punctuation "
        "and register of the email. Do not change any facts, invent nothing, remove "
        "no information, add no commentary of your own. Keep the line breaks. Reply "
        "only with the corrected email."
    )


def _clean(out: str) -> str:
    out = out.strip()
    if out.startswith("```"):
        lines = out.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        out = "\n".join(lines).strip()
    return out


class OllamaBackend:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def correct(self, text: str, language: str) -> LLMResult:
        if not text.strip():
            return LLMResult(text=text, ok=False, error="Nothing to correct.")
        prompt = f"{_instruction(language)}\n\n--- COURRIEL / EMAIL ---\n{text}"
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            return LLMResult(text=text, ok=False, error=f"Ollama HTTP {exc.code}: {detail}")
        except Exception as exc:
            return LLMResult(
                text=text,
                ok=False,
                error=f"Could not reach Ollama at {self.base_url} ({type(exc).__name__}).",
            )
        out = _clean(data.get("response") or "")
        if not out:
            return LLMResult(text=text, ok=False, error="Empty response from the model.")
        return LLMResult(text=out, ok=True)


# Cache loaded models by path — loading a GGUF is expensive.
_LLAMA_CACHE: dict = {}


class LlamaCppBackend:
    """In-process GGUF model via llama-cpp-python (optional dependency)."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def correct(self, text: str, language: str) -> LLMResult:
        if not text.strip():
            return LLMResult(text=text, ok=False, error="Nothing to correct.")
        try:
            from llama_cpp import Llama
        except ImportError:
            return LLMResult(
                text=text,
                ok=False,
                error="llama-cpp-python is not installed. Run: pip install llama-cpp-python",
            )
        if not self.model_path or not os.path.exists(self.model_path):
            return LLMResult(
                text=text,
                ok=False,
                error="Set a valid .gguf path in Settings (llama-cpp model path).",
            )
        try:
            llm = _LLAMA_CACHE.get(self.model_path)
            if llm is None:
                llm = Llama(model_path=self.model_path, n_ctx=4096, verbose=False)
                _LLAMA_CACHE[self.model_path] = llm
            result = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": _instruction(language)},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
            )
            out = _clean(result["choices"][0]["message"]["content"] or "")
        except Exception as exc:
            return LLMResult(text=text, ok=False, error=f"llama-cpp error: {type(exc).__name__}: {exc}")
        if not out:
            return LLMResult(text=text, ok=False, error="Empty response from the model.")
        return LLMResult(text=out, ok=True)


def get_backend(settings: Settings):
    if settings.llm_backend == LLMBackendType.llama_cpp:
        return LlamaCppBackend(settings.llama_model_path)
    return OllamaBackend(settings.llm_base_url, settings.llm_model)
