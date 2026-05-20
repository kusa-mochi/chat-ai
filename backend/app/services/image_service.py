import asyncio
import random
from typing import Any

import httpx

from app.config import settings


def _workflow(prompt_text: str) -> dict[str, Any]:
    seed = random.randint(1, 2_147_483_647)
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 24,
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
                "ckpt_name": settings.comfyui_checkpoint,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 768,
                "height": 512,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"anime style, cinematic lighting, japanese fantasy, {prompt_text}",
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, distorted, extra fingers",
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


async def generate_image(prompt_text: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        create_response = await client.post(
            f"{settings.comfyui_base_url}/prompt",
            json={"prompt": _workflow(prompt_text)},
        )
        create_response.raise_for_status()
        prompt_id = create_response.json().get("prompt_id")
        if not prompt_id:
            raise ValueError("ComfyUI prompt_id was not returned")

        for _ in range(40):
            await asyncio.sleep(1.5)
            history_response = await client.get(f"{settings.comfyui_base_url}/history/{prompt_id}")
            if history_response.status_code >= 400:
                continue

            history = history_response.json().get(prompt_id)
            if not history:
                continue

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
