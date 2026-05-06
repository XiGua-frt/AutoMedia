-- 知识库（RAG）表结构：utf8mb4 + InnoDB
-- 使用：mysql -uroot -p < sql/add_knowledge_tables.sql
-- Docker：已通过 docker-compose mysql init 挂载执行

USE ai_passage_creator;

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_document
(
    id                 VARCHAR(36)    NOT NULL COMMENT 'UUID',
    title              VARCHAR(500)   NOT NULL,
    platform           VARCHAR(50)    NULL,
    category           VARCHAR(100)   NULL,
    style              VARCHAR(50)    NULL,
    source_type        VARCHAR(20)    NULL COMMENT 'file_pdf / url / text 等',
    source_url         TEXT           NULL,
    quality_score      DECIMAL(3, 1)  NULL,
    tags               JSON           NULL COMMENT '["标签1","标签2"]',
    summary            TEXT           NULL,
    structure_summary  TEXT           NULL,
    viral_elements     JSON           NULL,
    status             VARCHAR(20)    NOT NULL DEFAULT 'active',
    created_at         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_platform (platform),
    INDEX idx_style (style),
    INDEX idx_quality_score (quality_score),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunk
(
    id                VARCHAR(36)   NOT NULL COMMENT 'UUID',
    doc_id            VARCHAR(36)   NOT NULL,
    chunk_index       INT           NOT NULL,
    section_title     VARCHAR(500)  NULL,
    chunk_type        VARCHAR(20)   NULL COMMENT 'body / title_block / summary',
    content           TEXT          NOT NULL,
    keywords          JSON          NULL,
    qdrant_point_id   VARCHAR(36)   NULL,
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_knowledge_chunk_document
        FOREIGN KEY (doc_id) REFERENCES knowledge_document (id) ON DELETE CASCADE,
    INDEX idx_doc_id (doc_id),
    INDEX idx_chunk_type (chunk_type),
    INDEX idx_qdrant_point_id (qdrant_point_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
