"""
VectorStore abstraction for Compliance Agent.

Two backends:
- InMemoryVectorStore  — 0 контейнеров, старт за миллисекунды, для CI/CD
- QdrantVectorStore    — persistent, для демонстрации «как в production»

Переключение через env: VECTOR_STORE=memory|qdrant
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Rule:
    rule_id: str
    text: str
    source_file: str


class VectorStore(ABC):
    @abstractmethod
    def add_rules(self, rules: List[Rule]) -> None: ...
    @abstractmethod
    def search(self, query: str, top_k: int = 3) -> List[Rule]: ...


class InMemoryVectorStore(VectorStore):
    """Keyword-based retrieval по атомарным .md-файлам."""

    def __init__(self) -> None:
        self._rules: List[Rule] = []

    def add_rules(self, rules: List[Rule]) -> None:
        self._rules.extend(rules)

    def search(self, query: str, top_k: int = 3) -> List[Rule]:
        q = query.lower()
        scored: List[tuple[int, Rule]] = []
        for rule in self._rules:
            score = sum(1 for w in q.split() if w in rule.text.lower())
            if score > 0:
                scored.append((score, rule))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]


class QdrantVectorStore(VectorStore):
    """Persistent backend для production-демо."""

    def __init__(self, url: str = "http://qdrant:6333", collection: str = "lna_rules") -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        self._client = QdrantClient(url=url)
        self._collection = collection
        
        # Замена устаревшего метода recreate_collection
        if self._client.collection_exists(collection_name=collection):
            self._client.delete_collection(collection_name=collection)

        self._client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

    def _embed(self, text: str) -> List[float]:
        import httpx
        r = httpx.post(
            "http://ollama:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    def add_rules(self, rules: List[Rule]) -> None:
        from qdrant_client.models import PointStruct
        points = [
            PointStruct(
                id=i,
                vector=self._embed(r.text),
                payload={"rule_id": r.rule_id, "text": r.text, "source_file": r.source_file},
            )
            for i, r in enumerate(rules)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def search(self, query: str, top_k: int = 3) -> List[Rule]:
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=self._embed(query),
            limit=top_k,
        )
        return [
            Rule(
                rule_id=h.payload["rule_id"],
                text=h.payload["text"],
                source_file=h.payload["source_file"],
            )
            for h in hits
        ]


def load_rules(policies_dir: Path) -> List[Rule]:
    rules: List[Rule] = []
    for md in sorted(policies_dir.glob("rule_*.md")):
        text = md.read_text(encoding="utf-8").strip()
        rule_id = md.stem
        rules.append(Rule(rule_id=rule_id, text=text, source_file=md.name))
    return rules


def build_store() -> VectorStore:
    mode = os.getenv("VECTOR_STORE", "memory").lower()
    if mode == "qdrant":
        return QdrantVectorStore()
    return InMemoryVectorStore()
