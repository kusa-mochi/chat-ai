from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.config import Settings


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = QdrantClient(url=settings.vector_url)

    def ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        existing = {collection.name for collection in collections}
        if self.settings.vector_collection in existing:
            return

        self.client.create_collection(
            collection_name=self.settings.vector_collection,
            vectors_config=qm.VectorParams(size=self.settings.embedding_dimension, distance=qm.Distance.COSINE),
        )

    def upsert_entry(self, story_id: str, entry_id: int, role: str, content: str, vector: list[float], is_active: bool = True) -> None:
        self.client.upsert(
            collection_name=self.settings.vector_collection,
            wait=True,
            points=[
                qm.PointStruct(
                    id=entry_id,
                    vector=vector,
                    payload={
                        "story_id": story_id,
                        "entry_id": entry_id,
                        "role": role,
                        "content": content,
                        "is_active": is_active,
                    },
                )
            ],
        )

    def set_entries_active(self, entry_ids: list[int], is_active: bool) -> None:
        if not entry_ids:
            return
        self.client.set_payload(
            collection_name=self.settings.vector_collection,
            payload={"is_active": is_active},
            points=entry_ids,
        )

    def search_by_story(self, story_id: str, query_vector: list[float], limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        hits = self.client.search(
            collection_name=self.settings.vector_collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=qm.Filter(
                must=[
                    qm.FieldCondition(key="story_id", match=qm.MatchValue(value=story_id)),
                    qm.FieldCondition(key="is_active", match=qm.MatchValue(value=True)),
                ]
            ),
        )
        return [hit.payload or {} for hit in hits]
