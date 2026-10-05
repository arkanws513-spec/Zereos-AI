"""Zereos image generation and editing tool backed by OpenAI GPT Image.

The API key is server-side only (OPENAI_API_KEY). Generated images are written into
the current workspace's generated-images directory and returned as Markdown so the
normal chat renderer can display them.

For edits, image_path must point to an image already available inside the current
workspace. The tool deliberately does not accept arbitrary filesystem paths or
remote URLs.
"""

from __future__ import annotations

import base64
import binascii
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from jenny.agent.tools.base import Tool, tool_parameters
from jenny.agent.tools.schema import StringSchema, tool_parameters_schema
from jenny.security.workspace_policy import _safe_expanduser
from jenny.utils.helpers import ensure_dir, safe_filename
from jenny.utils.path import atomic_write

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images"
DEFAULT_GENERATION_MODEL = "gpt-image-2.5-flare"
DEFAULT_EDIT_MODEL = "gpt-image-2.5-sunburst"
MAX_PROMPT_CHARS = 32_000
MAX_INPUT_BYTES = 20 * 1024 * 1024
TIMEOUT_S = 300.0


def _api_key() -> str | None:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    return value or None


def _safe_image_path(workspace: Path, raw: str) -> Path:
    candidate = (_safe_expanduser(workspace) / raw).resolve()
    root = _safe_expanduser(workspace).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("image_path must stay inside the current workspace") from exc
    if not candidate.is_file():
        raise ValueError("image_path does not exist")
    if candidate.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input image exceeds 20 MB")
    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("image_path must be PNG, JPG, JPEG, or WebP")
    return candidate


def _decode_b64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("OpenAI returned invalid image data") from exc


def _save_image(workspace: Path, data: bytes) -> Path:
    out_dir = ensure_dir(workspace / "generated-images")
    target = out_dir / f"zereos-image-{uuid.uuid4().hex[:10]}.png"
    atomic_write(target, data)
    logger.info("generate_image: saved {} ({} bytes)", target, len(data))
    return target


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "Detailed image prompt. Arabic text is allowed and should be reproduced exactly when requested.",
            min_length=1,
            max_length=MAX_PROMPT_CHARS,
        ),
        image_path=StringSchema(
            "Optional workspace-relative source image to edit. Leave empty for new generation.",
            nullable=True,
        ),
        size=StringSchema(
            "Output size, such as 1024x1024, 1536x1024, or 1024x1536.",
            default="1024x1024",
        ),
        quality=StringSchema(
            "Image quality: low, medium, high, xhigh, max, or auto.",
            default="high",
        ),
        n=StringSchema(
            "Number of images to create, from 1 to 4.",
            default="1",
        ),
        required=["prompt"],
    )
)
class GenerateImageTool(Tool):
    name = "generate_image"
    description = (
        "Generate a new image or edit an existing workspace image with OpenAI GPT Image. "
        "Use this for image creation, posters, illustrations, photorealistic scenes, "
        "Arabic text in images, and image edits. For an edit, provide image_path. "
        "The generated PNG is saved under generated-images/ and should be shown inline "
        "using the returned Markdown image link. Requires server-side OPENAI_API_KEY."
    )

    _scopes = {"core", "subagent"}

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return bool(_api_key())

    @classmethod
    def disabled_reason(cls, ctx: Any) -> str | None:
        return "OPENAI_API_KEY is not configured on the server."

    @classmethod
    def create(cls, ctx: Any) -> "GenerateImageTool":
        return cls(workspace=ctx.workspace)

    def __init__(self, workspace: str | Path, client: httpx.AsyncClient | None = None):
        self._workspace = _safe_expanduser(workspace)
        self._client = client

    async def execute(
        self,
        prompt: str,
        image_path: str | None = None,
        size: str = "1024x1024",
        quality: str = "high",
        n: str = "1",
        **_: Any,
    ) -> str:
        key = _api_key()
        if not key:
            return "Error: image generation is not configured (OPENAI_API_KEY missing)."

        prompt = str(prompt).strip()
        if not prompt:
            return "Error: prompt is empty."

        allowed_sizes = {"1024x1024", "1536x1024", "1024x1536", "auto"}
        allowed_quality = {"low", "medium", "high", "xhigh", "max", "auto"}
        try:
            count = max(1, min(4, int(n)))
        except (TypeError, ValueError):
            count = 1
        if size not in allowed_sizes:
            return f"Error: unsupported size {size!r}."
        if quality not in allowed_quality:
            return f"Error: unsupported quality {quality!r}."

        headers = {"Authorization": f"Bearer {key}"}
        data: dict[str, Any] = {
            "model": DEFAULT_EDIT_MODEL if image_path else DEFAULT_GENERATION_MODEL,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": count,
            "output_format": "png",
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_S)
        try:
            if image_path:
                source = _safe_image_path(self._workspace, image_path)
                with source.open("rb") as fh:
                    files = {"image[]": (source.name, fh, "application/octet-stream")}
                    response = await client.post(
                        f"{OPENAI_IMAGES_URL}/edits",
                        headers=headers,
                        data=data,
                        files=files,
                    )
            else:
                response = await client.post(
                    f"{OPENAI_IMAGES_URL}/generations",
                    headers=headers,
                    json=data,
                )
        except (httpx.HTTPError, OSError) as exc:
            return f"Error: image request failed: {exc}"
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:1000]
            return f"Error: OpenAI image request failed ({response.status_code}): {detail}"

        try:
            payload = response.json()
            images = payload.get("data") or []
            if not images:
                return "Error: OpenAI returned no image."
            outputs: list[str] = []
            for item in images:
                raw = item.get("b64_json")
                if not raw:
                    continue
                path = _save_image(self._workspace, _decode_b64(raw))
                rel = path.relative_to(self._workspace).as_posix()
                outputs.append(f"![Zereos image]({rel})")
            if not outputs:
                return "Error: OpenAI returned image metadata without image data."
            return "Generated image(s):\n\n" + "\n\n".join(outputs)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return f"Error: could not save generated image: {exc}"


TOOLS = [GenerateImageTool]
