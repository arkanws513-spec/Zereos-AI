"""Create LLM providers from config."""

from __future__ import annotations

import json
import os
from typing import Any

from jenny.config.schema import Config, ProviderConfig
from jenny.providers.base import GenerationSettings, LLMProvider
from jenny.providers.tls import build_ssl_context

__all__ = ["make_provider", "provider_fingerprint"]


def _make_provider_core(config: Config) -> LLMProvider:
    """Create a plain LLM provider from the active provider in config."""
    try:
        p = config.get_active_provider()
    except ValueError:
        # Production bootstrap: configure a fresh installation from Railway
        # secrets without putting API keys in config.json or the APK.
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_key2 = os.getenv("GEMINI_API_KEY2", "").strip()
        qwen_key = os.getenv("QWEN_API_KEY", "").strip()
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        if gemini_key or gemini_key2:
            p = ProviderConfig(
                name="Gemini",
                format="openai_compat",
                api_key=gemini_key or gemini_key2,
                api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_type="chat_completions",
            )
            if not config.agents.defaults.model:
                config.agents.defaults.model = "gemini-3.8-flash"
        elif qwen_key:
            p = ProviderConfig(
                name="Qwen",
                format="openai_compat",
                api_key=qwen_key,
                api_base="https://maas.qwencloudapi.com/compatible-mode/v1",
                api_type="chat_completions",
            )
            if not config.agents.defaults.model:
                config.agents.defaults.model = "qwen3.8-max"
        elif deepseek_key:
            p = ProviderConfig(
                name="DeepSeek",
                format="openai_compat",
                api_key=deepseek_key,
                api_base="https://api.deepseek.com",
                api_type="chat_completions",
            )
            if not config.agents.defaults.model:
                config.agents.defaults.model = "deepseek-flash"
        elif openai_key:
            p = ProviderConfig(
                name="OpenAI",
                format="openai_compat",
                api_key=openai_key,
                api_base="https://api.openai.com/v1",
                api_type="auto",
            )
            if not config.agents.defaults.model:
                config.agents.defaults.model = "gpt-5-mini"
        else:
            raise RuntimeError(
                "No provider configured. Add a provider in Settings or edit "
                "workspace/config.json to set providers.providers[0]."
            ) from None

    backend = p.format
    defaults = config.agents.defaults
    model = defaults.model

    if not p.api_key:
        raise RuntimeError(f"Provider '{p.name}': api_key is required.")

    ssl_context = build_ssl_context(p.ca_bundle, provider_name=p.name)

    if backend == "anthropic":
        from jenny.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
            extra_headers=p.extra_headers,
            extra_body=p.extra_body,
            extra_query=p.extra_query,
            api_type=p.api_type,
            ssl_context=ssl_context,
        )
    else:
        from jenny.providers.openai_compat_provider import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
            extra_headers=p.extra_headers,
            extra_body=p.extra_body,
            api_type=p.api_type,
            extra_query=p.extra_query,
            ssl_context=ssl_context,
        )

    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    provider.provider_name = p.name
    return provider


def make_provider(config: Config) -> LLMProvider:
    """Create the LLM provider from config."""
    return _make_provider_core(config)


def provider_fingerprint(config: Config) -> str:
    """Summarize all config read by make_provider without logging secrets."""
    try:
        provider: dict[str, Any] | None = config.get_active_provider().model_dump()
    except ValueError:
        provider = None
    defaults = config.agents.defaults
    payload = {
        "provider": provider,
        "model": defaults.model,
        "context_window_tokens": defaults.context_window_tokens,
        "temperature": defaults.temperature,
        "max_tokens": defaults.max_tokens,
        "reasoning_effort": defaults.reasoning_effort,
    }
    return json.dumps(payload, sort_keys=True, default=str)
