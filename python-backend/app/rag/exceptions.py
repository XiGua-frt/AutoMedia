"""RAG 模块自定义异常体系。

所有 RAG 相关异常均继承自 RAGBaseException，
调用方可统一捕获 RAGBaseException 处理 RAG 链路中的所有错误，
也可按需捕获具体子类做精细化处理。
"""


class RAGBaseException(Exception):
    """所有 RAG 异常的基类。

    提供统一的 message 属性，子类可直接复用。

    Attributes:
        message: 人类可读的错误描述。
    """

    def __init__(self, message: str = "RAG 处理异常") -> None:
        self.message = message
        super().__init__(self.message)


class DocumentLoadError(RAGBaseException):
    """文件或 URL 加载失败。

    典型场景：
    - 本地文件不存在或权限不足
    - 远程 URL 请求超时 / 返回非 200 状态码
    - 文件格式不受支持（如加密 PDF）
    """

    def __init__(self, message: str = "文档加载失败") -> None:
        super().__init__(message)


class TextCleanError(RAGBaseException):
    """文本清洗过程失败。

    典型场景：
    - HTML / Markdown 解析异常
    - 正则替换规则导致内容丢失
    - 编码转换失败
    """

    def __init__(self, message: str = "文本清洗失败") -> None:
        super().__init__(message)


class MetadataExtractError(RAGBaseException):
    """元数据提取失败。

    典型场景：
    - LLM 返回的 JSON 无法解析
    - 必填字段缺失（标题 / 平台 / 标签等）
    - LLM 调用超时或返回空结果
    """

    def __init__(self, message: str = "元数据提取失败") -> None:
        super().__init__(message)


class EmbeddingError(RAGBaseException):
    """Embedding 调用失败。

    典型场景：
    - DashScope Embedding API 返回错误
    - 输入文本超过模型最大 token 限制
    - API Key 无效或配额耗尽
    """

    def __init__(self, message: str = "Embedding 调用失败") -> None:
        super().__init__(message)


class VectorStoreError(RAGBaseException):
    """向量库读写失败。

    典型场景：
    - Qdrant 服务不可达
    - Collection 不存在或 schema 不匹配
    - 写入 / 删除操作超时
    """

    def __init__(self, message: str = "向量库读写失败") -> None:
        super().__init__(message)


class RetrievalError(RAGBaseException):
    """检索过程失败。

    典型场景：
    - 混合检索中 dense / sparse 任一路径异常
    - 元数据过滤条件非法
    - 结果合并或 MMR 去重阶段出错
    """

    def __init__(self, message: str = "检索失败") -> None:
        super().__init__(message)


class ChunkError(RAGBaseException):
    """文档切分失败。

    典型场景：
    - 切分后 chunk 数量为 0（文档过短或切分参数不合理）
    - Markdown Header 切分器解析异常
    - 递归切分超出最大递归深度
    """

    def __init__(self, message: str = "文档切分失败") -> None:
        super().__init__(message)
