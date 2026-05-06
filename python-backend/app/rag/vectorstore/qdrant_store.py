"""Qdrant 向量库存储实现。

封装 ``qdrant-client``，提供 Dense 写入与检索、可选 Sparse 向量写入、
Payload 过滤与 MMR 去重检索；集合不存在时自动创建。
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any, Final, Mapping, Sequence

from langchain.schema import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    Range,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.rag.exceptions import VectorStoreError

_LOGGER = logging.getLogger(__name__)

_DENSE_VECTOR_NAME: Final[str] = "dense"
_SPARSE_VECTOR_NAME: Final[str] = "sparse"

_PAYLOAD_METADATA_KEYS: Final[tuple[str, ...]] = (
    "knowledge_id",
    "chunk_id",
    "platform",
    "style",
    "category",
    "tags",
    "quality_score",
    "chunk_type",
    "section_title",
)

_SPARSE_META_INDICES: Final[str] = "sparse_indices"
_SPARSE_META_VALUES: Final[str] = "sparse_values"

_DISTANCE_ALIASES: Final[Mapping[str, Distance]] = {
    "cosine": Distance.COSINE,
    "Cosine": Distance.COSINE,
    "COSINE": Distance.COSINE,
    "euclid": Distance.EUCLID,
    "Euclid": Distance.EUCLID,
    "euclidean": Distance.EUCLID,
    "dot": Distance.DOT,
    "Dot": Distance.DOT,
    "manhattan": Distance.MANHATTAN,
}


class QdrantVectorStore:
    """Qdrant 向量库封装，实现 ``BaseVectorStore`` 协议约定的方法集合。

    使用命名向量 ``dense``（稠密）与 ``sparse``（稀疏，可选写入）。
    稀疏向量通过 ``Document.metadata`` 中的 ``sparse_indices`` /
    ``sparse_values`` 提供（便于二期接入 FastEmbed / BM25）；二者均存在时写入，
    且不会写入 Payload，以免污染业务字段。

    Attributes:
        client: 底层 ``QdrantClient`` 实例，只读场景可直接使用。
    """

    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        vector_size: int = 1536,
        distance: str = "Cosine",
    ) -> None:
        """初始化 Qdrant 向量库客户端。

        Args:
            host: Qdrant 服务主机名。若为特殊值 ``":memory:"``，则使用进程内内存实例
                （``port`` 被忽略），便于单元测试。
            port: REST API 端口（默认 6333）。
            collection_name: 集合名称。
            vector_size: 稠密向量维度，需与 Embedding 模型输出一致。
            distance: 距离度量，支持 ``Cosine`` / ``Euclid`` / ``Dot`` 等（大小写不敏感别名见实现）。
        """
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._distance = _parse_distance(distance)
        if host.strip() == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(host=host, port=port)

    def ensure_collection(self) -> None:
        """若集合不存在则创建；已存在则跳过。

        创建的集合包含命名稠密向量 ``dense`` 与命名稀疏向量 ``sparse``（稀疏可在写入时省略）。

        Raises:
            VectorStoreError: 创建集合失败时抛出。
        """
        try:
            if self.client.collection_exists(self._collection_name):
                return
            self.client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    _DENSE_VECTOR_NAME: VectorParams(
                        size=self._vector_size,
                        distance=self._distance,
                    ),
                },
                sparse_vectors_config={
                    _SPARSE_VECTOR_NAME: SparseVectorParams(),
                },
            )
            _LOGGER.info(
                "已创建 Qdrant 集合: %s (dense_dim=%s)",
                self._collection_name,
                self._vector_size,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"创建或检查 Qdrant 集合失败: {exc}") from exc

    def add_documents(
        self,
        docs: list[Document],
        embeddings: list[list[float]],
    ) -> list[str]:
        """批量写入文档向量及 Payload，返回 Point ID 列表。

        Args:
            docs: LangChain ``Document`` 列表；``page_content`` 写入 Payload 的 ``page_content``；
                规范元数据字段从 ``metadata`` 映射到 Payload。
            embeddings: 与 ``docs`` 一一对应的稠密向量。

        Returns:
            每个点对应的 ID 字符串列表（与 ``docs`` 等长）。

        Raises:
            VectorStoreError: 参数不合法或写入失败时抛出。
        """
        if len(docs) != len(embeddings):
            raise VectorStoreError(
                f"docs 与 embeddings 长度不一致: {len(docs)} != {len(embeddings)}",
            )
        self.ensure_collection()
        points: list[PointStruct] = []
        ids: list[str] = []
        try:
            for doc, emb in zip(docs, embeddings, strict=True):
                if len(emb) != self._vector_size:
                    raise VectorStoreError(
                        f"向量维度 {len(emb)} 与集合配置 vector_size={self._vector_size} 不一致",
                    )
                pid = _stable_point_id(doc.metadata or {})
                ids.append(pid)
                vec: dict[str, Any] = {_DENSE_VECTOR_NAME: emb}
                sparse = _sparse_vector_from_metadata(doc.metadata or {})
                if sparse is not None:
                    vec[_SPARSE_VECTOR_NAME] = sparse
                payload = _document_to_payload(doc)
                points.append(PointStruct(id=pid, vector=vec, payload=payload))
            if points:
                self.client.upsert(collection_name=self._collection_name, points=points)
        except VectorStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant upsert 失败: {exc}") from exc
        return ids

    def similarity_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[Document]:
        """稠密向量相似度检索，支持 Payload 过滤。

        Args:
            query_vector: 查询稠密向量。
            top_k: 返回条数上限。
            filters: 过滤条件字典；字符串精确匹配、数值区间、列表 ``MatchAny`` 等，见 ``_build_filter``。

        Returns:
            按相似度分数降序排列的 ``Document`` 列表。

        Raises:
            VectorStoreError: 检索失败时抛出。
        """
        if len(query_vector) != self._vector_size:
            raise VectorStoreError(
                f"query_vector 维度 {len(query_vector)} 与 vector_size={self._vector_size} 不一致",
            )
        flt = self._build_filter(filters)
        try:
            resp = self.client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                using=_DENSE_VECTOR_NAME,
                query_filter=flt,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant 检索失败: {exc}") from exc
        return [_scored_point_to_document(p) for p in resp.points]

    def mmr_search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        filters: dict | None = None,
    ) -> list[Document]:
        """最大边际相关性（MMR）检索，减轻结果冗余。

        先从 Qdrant 取 ``fetch_k`` 条候选（含向量），再在本地做 MMR 重排，
        返回 ``top_k`` 条 ``Document``。

        Args:
            query_vector: 查询稠密向量。
            top_k: 最终返回条数。
            fetch_k: 从向量库拉取的候选条数，应不小于 ``top_k``。
            lambda_mult: 权衡相关性与多样性的系数，越大越偏向相关性。
            filters: 与 ``similarity_search`` 相同的过滤字典。

        Returns:
            MMR 重排后的 ``Document`` 列表。

        Raises:
            VectorStoreError: 检索或本地计算失败时抛出。
        """
        if fetch_k < top_k:
            fetch_k = top_k
        if len(query_vector) != self._vector_size:
            raise VectorStoreError(
                f"query_vector 维度 {len(query_vector)} 与 vector_size={self._vector_size} 不一致",
            )
        flt = self._build_filter(filters)
        try:
            resp = self.client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                using=_DENSE_VECTOR_NAME,
                query_filter=flt,
                limit=fetch_k,
                with_payload=True,
                with_vectors=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant MMR 候选检索失败: {exc}") from exc

        candidates: list[dict[str, Any]] = []
        for p in resp.points:
            doc = _scored_point_to_document(p)
            vec = _extract_dense_vector(p.vector)
            if vec is None:
                raise VectorStoreError("MMR 需要向量数据，但返回结果中缺少 dense 向量")
            qn = _l2_normalize(query_vector)
            vn = _l2_normalize(vec)
            rel = float(p.score) if p.score is not None else _dot(qn, vn)
            candidates.append({"doc": doc, "vec": vec, "vec_norm": vn, "rel": rel})

        order_idx = _mmr_order(candidates, top_k, lambda_mult)
        return [candidates[i]["doc"] for i in order_idx]

    def delete(self, ids: list[str]) -> None:
        """按 Point ID 批量删除。

        Args:
            ids: Qdrant 点 ID 列表（与 ``add_documents`` 返回值对应）。

        Raises:
            VectorStoreError: 删除调用失败时抛出。
        """
        if not ids:
            return
        try:
            self.client.delete(
                collection_name=self._collection_name,
                points_selector=PointIdsList(points=list(ids)),
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant 删除失败: {exc}") from exc

    def _build_filter(self, filters: dict | None) -> Filter | None:
        """将业务 ``filters`` 字典转换为 Qdrant ``Filter``（供单测或子类扩展调用）。"""
        return _filters_to_qdrant(filters)


def _parse_distance(name: str) -> Distance:
    key = (name or "").strip()
    if key in _DISTANCE_ALIASES:
        return _DISTANCE_ALIASES[key]
    raise VectorStoreError(f"不支持的 distance: {name!r}")


def _stable_point_id(metadata: Mapping[str, Any]) -> str:
    """根据 ``chunk_id`` 生成稳定 UUID 字符串；否则随机 UUID。"""
    raw = metadata.get("chunk_id") or metadata.get("point_id")
    if raw is not None and str(raw).strip() != "":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk:{raw}"))
    return str(uuid.uuid4())


def _sparse_vector_from_metadata(metadata: Mapping[str, Any]) -> SparseVector | None:
    """从 metadata 解析稀疏向量（二期 BM25 / FastEmbed 写入约定）。"""
    idx = metadata.get(_SPARSE_META_INDICES)
    vals = metadata.get(_SPARSE_META_VALUES)
    if idx is None and vals is None:
        return None
    if (idx is None) ^ (vals is None):
        raise VectorStoreError("sparse_indices 与 sparse_values 须同时提供或同时省略")
    if isinstance(idx, (str, bytes)) or isinstance(vals, (str, bytes)):
        raise VectorStoreError("sparse_indices / sparse_values 不能为字符串类型")
    if not isinstance(idx, Sequence) or not isinstance(vals, Sequence):
        raise VectorStoreError(
            "sparse_indices / sparse_values 必须为与权重等长的序列类型",
        )
    indices = [int(i) for i in idx]
    values = [float(v) for v in vals]
    if len(indices) != len(values):
        raise VectorStoreError("sparse_indices 与 sparse_values 长度不一致")
    return SparseVector(indices=indices, values=values)


def _document_to_payload(doc: Document) -> dict[str, Any]:
    """将 LangChain Document 转为 Qdrant Payload（含规范字段）。"""
    payload: dict[str, Any] = {"page_content": doc.page_content}
    meta = doc.metadata or {}
    for key in _PAYLOAD_METADATA_KEYS:
        if key not in meta or meta[key] is None:
            continue
        if key == "tags" and not isinstance(meta[key], list):
            raise VectorStoreError("metadata.tags 必须为 list[str]")
        if key == "quality_score" and not isinstance(meta[key], (int, float)):
            raise VectorStoreError("metadata.quality_score 必须为数值类型")
        if key == "chunk_type" and str(meta[key]) not in ("body", "title", "summary"):
            _LOGGER.debug(
                "chunk_type=%s 不在推荐枚举 body|title|summary 内，仍原样写入",
                meta[key],
            )
        payload[key] = meta[key]
    return payload


def _scored_point_to_document(point: Any) -> Document:
    """将 ``ScoredPoint`` 转回 ``Document``。"""
    payload = dict(point.payload or {})
    page = str(payload.pop("page_content", ""))
    return Document(page_content=page, metadata=payload)


def _extract_dense_vector(vector: Any) -> list[float] | None:
    """从 ``query_points`` 返回的 vector 字段提取 ``dense`` 向量。"""
    if vector is None:
        return None
    if isinstance(vector, dict):
        dense = vector.get(_DENSE_VECTOR_NAME)
        if dense is not None:
            return [float(x) for x in dense]
    if isinstance(vector, (list, tuple)):
        return [float(x) for x in vector]
    return None


def _filters_to_qdrant(filters: dict | None) -> Filter | None:
    """将业务 filters 转为 Qdrant Filter。

    规则概要：
    - 字符串 / 整型 / 浮点 / 布尔标量 → ``MatchValue``
    - 列表（如 ``tags``）→ ``MatchAny``（匹配任一元素）
    - 值类型为 ``dict`` 且含 ``gte`` / ``lte`` / ``gt`` / ``lt`` → ``Range``
    - 键名 ``field__gte`` / ``field__lte`` 等形式合并为同一字段的 ``Range``
    """
    if not filters:
        return None
    must: list[FieldCondition] = []
    used_keys: set[str] = set()

    range_bucket: dict[str, dict[str, float]] = {}
    for key, raw in filters.items():
        if "__" not in key:
            continue
        field, op = key.rsplit("__", 1)
        if op.lower() not in ("gte", "lte", "gt", "lt"):
            continue
        range_bucket.setdefault(field, {})[op.lower()] = float(raw)
        used_keys.add(key)

    for field, bounds in range_bucket.items():
        used_keys.add(field)
        must.append(
            FieldCondition(
                key=field,
                range=Range(
                    gte=bounds.get("gte"),
                    lte=bounds.get("lte"),
                    gt=bounds.get("gt"),
                    lt=bounds.get("lt"),
                ),
            ),
        )

    for key, value in filters.items():
        if key in used_keys:
            continue
        if isinstance(value, dict) and any(
            k in value for k in ("gte", "lte", "gt", "lt")
        ):
            must.append(
                FieldCondition(
                    key=key,
                    range=Range(
                        gte=value.get("gte"),
                        lte=value.get("lte"),
                        gt=value.get("gt"),
                        lt=value.get("lt"),
                    ),
                ),
            )
            continue
        if isinstance(value, list):
            must.append(FieldCondition(key=key, match=MatchAny(any=value)))
            continue
        if isinstance(value, (str, int, float, bool)):
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))
            continue
        raise VectorStoreError(f"无法解析的过滤条件: {key}={value!r}")

    return Filter(must=must) if must else None


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


def _l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return [0.0] * len(vec)
    return [float(x) / norm for x in vec]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    return _dot(_l2_normalize(a), _l2_normalize(b))


def _mmr_order(
    candidates: list[dict[str, Any]],
    top_k: int,
    lambda_mult: float,
) -> list[int]:
    """返回选中的候选下标序列（长度为 ``min(top_k, len(candidates))``）。"""
    if not candidates:
        return []

    selected: list[int] = []
    remaining = set(range(len(candidates)))
    first = max(remaining, key=lambda i: candidates[i]["rel"])
    selected.append(first)
    remaining.remove(first)

    while len(selected) < top_k and remaining:
        best_i: int | None = None
        best_score = -float("inf")
        for i in remaining:
            diversity = max(
                _cosine_similarity(candidates[i]["vec"], candidates[j]["vec"])
                for j in selected
            )
            score = lambda_mult * candidates[i]["rel"] - (1.0 - lambda_mult) * diversity
            if score > best_score:
                best_score = score
                best_i = i
        if best_i is None:
            break
        selected.append(best_i)
        remaining.remove(best_i)
    return selected
