"""
Unified LLM client using OpenRouter.
Routes requests through 3 cheap models: GPT-4o-mini, Claude 3.5 Haiku, Gemini 2.0 Flash.
Falls back to direct Gemini API if no OpenRouter key.
"""
import json
import logging
import os
import threading
import time

import requests

logger = logging.getLogger("apps")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# 3 cheap models — one from each provider
MODELS = {
    "gpt": "openai/gpt-4o-mini",
    "claude": "anthropic/claude-3.5-haiku",
    "gemini": "google/gemini-2.0-flash-001",
}

MODEL_LABELS = {
    "openai/gpt-4o-mini": "GPT-4o Mini",
    "anthropic/claude-3.5-haiku": "Claude 3.5 Haiku",
    "google/gemini-2.0-flash-001": "Gemini 2.0 Flash",
    "gemini-direct": "Gemini 2.0 Flash (Direct)",
}

# Default rotation order
MODEL_ORDER = ["gemini", "gpt", "claude"]

_call_counter = 0

# Cache availability check so we don't re-check every call
_availability_cache = None

# ── Thread-local log collector ────────────────────────────────────────────
# Each analysis thread gets its own log list

_thread_local = threading.local()


def start_log_collection():
    """Start collecting LLM logs for the current thread."""
    _thread_local.logs = []


def get_collected_logs() -> list[dict]:
    """Get all collected LLM logs for the current thread and clear."""
    logs = getattr(_thread_local, "logs", [])
    _thread_local.logs = []
    return logs


def _log_call(model: str, purpose: str, prompt: str, response: str, status: str, duration_ms: int):
    """Record an LLM call to the thread-local log."""
    logs = getattr(_thread_local, "logs", None)
    if logs is None:
        return  # Not collecting

    label = MODEL_LABELS.get(model, model)
    logs.append({
        "model": label,
        "model_id": model,
        "purpose": purpose,
        "prompt": prompt[:500],
        "response": response[:2000],
        "status": status,
        "duration_ms": duration_ms,
    })


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_openrouter_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY", "").strip() or None


def _get_google_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY", "").strip() or None


def _pick_model(preferred: str | None = None) -> str:
    """Pick a model. If preferred is set, use that. Otherwise rotate."""
    if preferred and preferred in MODELS:
        return MODELS[preferred]

    global _call_counter
    _call_counter += 1
    provider = MODEL_ORDER[_call_counter % len(MODEL_ORDER)]
    return MODELS[provider]


def is_available() -> bool:
    """Check if any LLM is available."""
    global _availability_cache
    if _availability_cache is not None:
        return _availability_cache

    if _get_openrouter_key():
        _availability_cache = True
        return True

    if _get_google_key():
        _availability_cache = True
        return True

    _availability_cache = False
    logger.warning("No LLM API key found. Set OPENROUTER_API_KEY or GOOGLE_API_KEY in .env")
    return False


# ── Main API ──────────────────────────────────────────────────────────────

def ask_llm(
    prompt: str,
    preferred_provider: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    purpose: str = "",
) -> str:
    """
    Send a prompt to an LLM via OpenRouter, or direct Gemini as fallback.
    Returns response text string. Empty string on failure.
    """
    if not is_available():
        return ""

    openrouter_key = _get_openrouter_key()

    if openrouter_key:
        return _call_openrouter(prompt, preferred_provider, max_tokens, temperature, openrouter_key, purpose)
    else:
        return _call_gemini_direct(prompt, purpose)


def _call_openrouter(
    prompt: str, preferred_provider: str | None,
    max_tokens: int, temperature: float, api_key: str,
    purpose: str = "",
) -> str:
    """Call OpenRouter API."""
    model = _pick_model(preferred_provider)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://optiminastic.com",
        "X-Title": "GEO Analyzer",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    prompt_preview = prompt[:120].replace('\n', ' ')
    logger.info("[LLM REQUEST] >> %s | %s | prompt: \"%s...\"", model, purpose, prompt_preview)

    t0 = time.time()
    try:
        resp = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        duration_ms = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            response_preview = content[:200].replace('\n', ' ')
            logger.info("[LLM RESPONSE] << %s | %dms | %d chars | \"%s...\"", model, duration_ms, len(content), response_preview)
            _log_call(model, purpose, prompt, content.strip(), "success", duration_ms)
            return content.strip()

        logger.warning("[LLM FAILED] << %s | HTTP %d: %s", model, resp.status_code, resp.text[:200])
        _log_call(model, purpose, prompt, f"HTTP {resp.status_code}", "error", duration_ms)
        return _retry_with_next(prompt, model, max_tokens, temperature, api_key, headers, purpose)

    except requests.Timeout:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("OpenRouter timeout for %s", model)
        _log_call(model, purpose, prompt, "Timeout", "error", duration_ms)
        return _retry_with_next(prompt, model, max_tokens, temperature, api_key, headers, purpose)
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("OpenRouter error for %s: %s", model, exc)
        _log_call(model, purpose, prompt, str(exc), "error", duration_ms)
        return ""


def _retry_with_next(
    prompt: str, failed_model: str, max_tokens: int, temperature: float,
    api_key: str, headers: dict, purpose: str = "",
) -> str:
    """Try the next model if the first one fails."""
    all_models = list(MODELS.values())
    for model in all_models:
        if model == failed_model:
            continue

        t0 = time.time()
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            resp = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            duration_ms = int((time.time() - t0) * 1000)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                logger.info("Fallback to %s succeeded (%dms)", model, duration_ms)
                _log_call(model, purpose + " (retry)", prompt, content.strip(), "success", duration_ms)
                return content.strip()
        except Exception:
            continue

    return ""


def _call_gemini_direct(prompt: str, purpose: str = "") -> str:
    """Direct Gemini API call -- used when no OpenRouter key is set."""
    google_key = _get_google_key()
    if not google_key:
        return ""

    prompt_preview = prompt[:120].replace('\n', ' ')
    logger.info("[LLM REQUEST] >> gemini-direct | %s | prompt: \"%s...\"", purpose, prompt_preview)

    t0 = time.time()
    try:
        import google.generativeai as genai

        genai.configure(api_key=google_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        duration_ms = int((time.time() - t0) * 1000)
        response_preview = text[:200].replace('\n', ' ')
        logger.info("[LLM RESPONSE] << gemini-direct | %dms | %d chars | \"%s...\"", duration_ms, len(text), response_preview)
        _log_call("gemini-direct", purpose, prompt, text, "success", duration_ms)
        return text
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("[LLM FAILED] << gemini-direct | %s", exc)
        _log_call("gemini-direct", purpose, prompt, str(exc), "error", duration_ms)
        return ""


def ask_multiple_llms(prompt: str, providers: list[str] | None = None, purpose: str = "") -> dict[str, str]:
    """
    Ask the same prompt to multiple LLMs and return all responses.
    Useful for AI visibility probes -- test across providers.

    Returns: {"gpt": "response...", "claude": "response...", "gemini": "response..."}
    """
    if not is_available():
        return {}

    if providers is None:
        providers = list(MODELS.keys())

    # If only direct Gemini is available (no OpenRouter), just use that
    if not _get_openrouter_key():
        result = _call_gemini_direct(prompt, purpose)
        return {"gemini": result} if result else {}

    results = {}
    for provider in providers:
        response = ask_llm(prompt, preferred_provider=provider, purpose=purpose)
        results[provider] = response

    return results
