import math
import os
import logging
import hashlib
from apps.chatbot.ai_engine.models import KnowledgeChunk

from django.db import connection

logger = logging.getLogger(__name__)

_openai_client = None
_cached_openai_key = None

def _get_openai_client(api_key: str):
    """Cached singleton getter for OpenAI API client to prevent socket leaks."""
    global _openai_client, _cached_openai_key
    if _openai_client is None or _cached_openai_key != api_key:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=api_key)
            _cached_openai_key = api_key
        except Exception as e:
            logger.error("Failed to initialize OpenAI client singleton: %s", e)
            return None
    return _openai_client

def _get_lightweight_feature_vector(text: str, dimensions: int = 384) -> list[float]:
    """
    Lightweight, zero-memory deterministic feature vectorizer.
    Generates a 384-dimensional normalized float vector for pgvector (CosineDistance)
    without requiring PyTorch or heavy C++ deep learning libraries.
    """
    words = text.lower().split()
    vec = [0.0] * dimensions
    for word in words:
        # Hash word into dimension index and value
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dimensions
        val = 1.0 + (h % 5) * 0.1
        vec[idx] += val

    mag = math.sqrt(sum(v * v for v in vec))
    return [v / mag for v in vec] if mag > 0 else vec

def get_text_embedding(text: str, dimensions: int = 384) -> list[float]:
    """
    Generates a normalized float vector embedding for text.
    Supports OpenAI API when OPENAI_API_KEY is configured, or lightweight zero-memory feature vectorizer.
    """
    if not text:
        return [0.0] * dimensions

    # Optional OpenAI Neural Embedding Engine
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        client = _get_openai_client(openai_key)
        if client:
            try:
                resp = client.embeddings.create(
                    input=[text[:1000]],
                    model="text-embedding-3-small",
                    dimensions=dimensions,
                )
                raw_embedding = resp.data[0].embedding
                mag = math.sqrt(sum(v * v for v in raw_embedding))
                return [v / mag for v in raw_embedding] if mag > 0 else raw_embedding
            except Exception as e:
                logger.warning(f"OpenAI embedding fallback: {e}")

    # Fallback: Lightweight zero-memory feature vectorizer (Guarantees zero OOM on Render 512MB tier)
    return _get_lightweight_feature_vector(text, dimensions=dimensions)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two vector lists."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_knowledge_base(query: str, category: str = None, top_k: int = 3):
    """
    Searches KnowledgeChunk for relevant chunks based on vector cosine similarity.
    Supports pgvector CosineDistance in PostgreSQL and fallback in-memory cosine similarity
    for SQLite or development environments.
    """
    if not query or not query.strip():
        return []

    query_vec = get_text_embedding(query.strip(), dimensions=384)

    qs = KnowledgeChunk.objects.all()
    if category:
        qs = qs.filter(category=category)

    if not qs.exists():
        return []

    # If running on PostgreSQL with pgvector
    if connection.vendor == 'postgresql':
        try:
            from pgvector.django import CosineDistance
            return list(qs.annotate(distance=CosineDistance('embedding', query_vec)).order_by('distance')[:top_k])
        except Exception as e:
            logger.warning(f"pgvector query failed, falling back to python cosine similarity: {e}")

    # In-memory cosine similarity for SQLite or non-pgvector environments
    scored_chunks = []
    for chunk in qs:
        chunk_vec = chunk.embedding_json or chunk.embedding
        if chunk_vec and isinstance(chunk_vec, list):
            score = cosine_similarity(query_vec, chunk_vec)
        else:
            score = 0.1 if any(w in chunk.content.lower() for w in query.lower().split()) else 0.0
        scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return [chunk for score, chunk in scored_chunks[:top_k] if score > 0.0]


