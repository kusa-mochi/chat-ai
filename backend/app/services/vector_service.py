import uuid
from typing import Any

import httpx

from app.config import settings


async def ensure_collection(vector_size: int) -> None:
    payload = {
        "vectors": {
            "size": vector_size,
            "distance": "Cosine",
        }
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.put(f"{settings.qdrant_url}/collections/{settings.qdrant_collection}", json=payload)


async def upsert_context(
    *,
    story_id: str,
    branch_id: str,
    message_id: str,
    role: str,
    kind: str,
    content: str,
    vector: list[float],
) -> None:
    payload = {
        "points": [
            {
                "id": str(uuid.uuid4()),
                "vector": vector,
                "payload": {
                    "story_id": story_id,
                    "branch_id": branch_id,
                    "message_id": message_id,
                    "role": role,
                    "kind": kind,
                    "content": content,
                },
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.put(
            f"{settings.qdrant_url}/collections/{settings.qdrant_collection}/points",
            json=payload,
        )


async def search_context(story_id: str, vector: list[float], limit: int = 5) -> list[str]:
    payload: dict[str, Any] = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "filter": {
            "must": [
                {
                    "key": "story_id",
                    "match": {
                        "value": story_id,
                    },
                }
            ]
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.qdrant_url}/collections/{settings.qdrant_collection}/points/search",
            json=payload,
        )

    if response.status_code >= 400:
        return []

    data = response.json()
    points = data.get("result", [])
    contexts: list[str] = []
    for point in points:
        payload_item = point.get("payload", {})
        text = payload_item.get("content")
        if text:
            contexts.append(text)
    return contexts
