import asyncio
import random
from typing import Any

import httpx

from app.config import settings


def _workflow(prompt_text: str, checkpoint_name: str) -> dict[str, Any]:
    seed = random.randint(1, 2_147_483_647)
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 8,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": checkpoint_name,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": (
                    "masterpiece, best quality, cute, kawaii, "
                    "japanese anime style, expressive face, soft lighting, "
                    f"{prompt_text}"
                ),
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, bad anatomy, extra fingers, watermark, text, logo",
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "story",
                "images": ["8", 0],
            },
        },
    }


def _extract_checkpoint_names(object_info: dict[str, Any]) -> list[str]:
    node = object_info.get("CheckpointLoaderSimple", {})
    required = node.get("input", {}).get("required", {})
    ckpt_name_field = required.get("ckpt_name")
    if not isinstance(ckpt_name_field, list) or not ckpt_name_field:
        return []

    names = ckpt_name_field[0]
    if not isinstance(names, list):
        return []

    return [str(name) for name in names if isinstance(name, str) and name]


def _extract_history_error_message(history_entry: dict[str, Any]) -> str | None:
    status = history_entry.get("status")
    if not isinstance(status, dict):
        return None

    if status.get("status_str") != "error":
        return None

    messages = status.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, list) or len(item) < 2:
                continue
            payload = item[1]
            if isinstance(payload, dict):
                detail = payload.get("exception_message") or payload.get("error")
                if isinstance(detail, str) and detail.strip():
                    return detail.strip()

    return "ComfyUI execution failed"


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    attempts: int = 8,
    delay_seconds: float = 1.0,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            if method == "GET":
                return await client.get(url)
            return await client.post(url, json=json_body)
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        ) as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(delay_seconds)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("ComfyUI request failed")


async def _resolve_checkpoint_name(client: httpx.AsyncClient) -> str:
    configured = settings.comfyui_checkpoint.strip()

    try:
        info_response = await client.get(
            f"{settings.comfyui_base_url}/object_info/CheckpointLoaderSimple"
        )
        info_response.raise_for_status()
        available = _extract_checkpoint_names(info_response.json())
    except Exception:
        # Preserve previous behavior if capability probing is unavailable.
        if configured:
            return configured
        raise RuntimeError("ComfyUI checkpoint could not be resolved")

    if configured and configured in available:
        return configured
    if available:
        return available[0]

    if configured:
        raise RuntimeError(
            "ComfyUI checkpoint is not available. "
            f"Configured COMFYUI_CHECKPOINT='{configured}', but no checkpoints are installed."
        )
    raise RuntimeError("No ComfyUI checkpoints are installed")


async def generate_image(prompt_text: str) -> str:
    # Internal docker service calls should not go through host proxy settings.
    async with httpx.AsyncClient(timeout=120.0, trust_env=False, follow_redirects=False) as client:
        checkpoint_name = await _resolve_checkpoint_name(client)
        create_response = await _request_with_retry(
            client,
            "POST",
            f"{settings.comfyui_base_url}/prompt",
            json_body={"prompt": _workflow(prompt_text, checkpoint_name)},
            attempts=12,
            delay_seconds=1.5,
        )
        if create_response.status_code >= 400:
            detail = create_response.text.strip()
            if len(detail) > 300:
                detail = detail[:300] + "..."
            raise RuntimeError(
                f"ComfyUI prompt request failed ({create_response.status_code}): {detail}"
            )
        prompt_id = create_response.json().get("prompt_id")
        if not prompt_id:
            raise ValueError("ComfyUI prompt_id was not returned")

        # CPU mode or first-run model warmup can take several minutes.
        for _ in range(400):
            await asyncio.sleep(1.5)
            history_response = await _request_with_retry(
                client,
                "GET",
                f"{settings.comfyui_base_url}/history/{prompt_id}",
                attempts=4,
                delay_seconds=0.6,
            )
            if history_response.status_code >= 400:
                continue

            history = history_response.json().get(prompt_id)
            if not history:
                continue

            error_message = _extract_history_error_message(history)
            if error_message:
                raise RuntimeError(f"ComfyUI execution failed: {error_message}")

            outputs = history.get("outputs", {})
            node_output = outputs.get("9", {})
            images = node_output.get("images", [])
            if not images:
                continue

            image = images[0]
            filename = image.get("filename")
            subfolder = image.get("subfolder", "")
            file_type = image.get("type", "output")
            if filename is None:
                continue

            return (
                f"{settings.comfyui_base_url}/view?filename={filename}"
                f"&subfolder={subfolder}&type={file_type}"
            )

    raise TimeoutError("ComfyUI image generation timed out")
