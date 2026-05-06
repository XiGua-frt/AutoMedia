# `cos_service.py` 服务说明

## 该文件封装的服务是做什么的？

`python-backend/app/services/cos_service.py` 封装的是**腾讯云 COS（对象存储）上传服务**，核心用途是把各种来源的图片统一上传到你自己的 COS Bucket，并返回可访问的 COS URL。

一句话：**它是图片资源的“统一落地层”，把外部图片链接/字节数据转成你系统可控的存储地址。**

---

## 为什么需要这个服务？

在你的多 Agent 图片链路里，图片可能来自很多渠道：
- 图库 URL（Pexels、Iconify、表情包等）
- AI 生图结果（可能是 URL、base64/data URL、二进制）
- 降级图片（fallback）

如果不做统一上传，会有这些问题：
- 外链不稳定（对方资源失效、限流、跨域策略变化）
- 域名不统一（前端缓存和权限策略难做）
- 难做运维治理（无法统一审计、生命周期管理）

`CosService` 就是为了解决这件事：**统一接收 -> 统一上传 -> 统一返回 COS 域名 URL**。

---

## 核心能力拆解

### 1) 初始化 COS 客户端
- 在 `__init__` 中用 `CosConfig + CosS3Client` 初始化腾讯云 SDK
- 从 `settings` 读取 `region / secret_id / secret_key / bucket`
- 同时初始化 `httpx.AsyncClient`，用于下载 URL 图片

### 2) `upload_image(image_url, folder)`
- 旧接口，输入是图片 URL
- 先下载 URL 内容，再上传 COS
- 成功返回 COS URL
- 失败降级：返回原始 `image_url`

### 3) `upload_image_data(image_data, folder)`（主力接口）
- 支持三种输入格式（第 5 期重点）：
  - `BYTES`：直接用字节上传
  - `DATA_URL`：先解析 data URL，再上传
  - `URL`：先下载 URL，再上传
- 根据 `image_data` 自动推断扩展名和 `ContentType`
- 成功返回 COS URL
- 失败策略：
  - `URL` 类型失败：返回原始 URL（可用性优先）
  - 其他类型失败：返回 `None`

### 4) `use_direct_url(image_url)`
- 明确“跳过 COS，直接用外链”的兜底接口

### 5) `close()`
- 关闭 `httpx.AsyncClient`，避免连接泄漏

---

## 代码中的关键设计点

- **多数据格式兼容**：`ImageData + DataType` 让上层无需关心底层图片载体类型
- **可用性优先**：上传失败不直接炸主流程，URL 类型可回退原始链接
- **路径隔离**：通过 `folder` 区分来源目录（如 `pexels/`、`mermaid/`），便于后续治理
- **类型正确性**：`ContentType=image_data.mime_type`，避免统一写死 `image/jpeg`
- **唯一命名**：`uuid.uuid4()` 避免文件名冲突

---

## 在项目中的典型调用位置

该服务主要由 `image_service_strategy.py` 使用：

1. 各图片服务先产出 `ImageData`
2. `ImageServiceStrategy.get_image_and_upload()` 调 `CosService.upload_image_data(...)`
3. 返回统一 COS URL 给 `ArticleAgentService`，再写入 `state.images`

也就是说：`CosService` 位于**图片生成/检索结果**和**业务最终可用链接**之间的关键一层。

---

## 常见面试表达（可直接说）

- `CosService` 是对象存储适配层，负责将多来源图片统一上传到 COS，输出稳定可控 URL。  
- 它通过 `ImageData` 抽象屏蔽输入差异，支持 URL、bytes、data URL 三种格式。  
- 失败策略采用可用性优先：URL 上传失败可回退原始链接，避免主链路中断。  
- 通过 `folder + UUID + mime_type` 实现可治理、低冲突、类型正确的对象存储写入。  

---

## 一句话总结

`cos_service.py` 的本质是：**把“图片获取”与“图片持久化访问”解耦，提供统一、稳定、可治理的图片落盘能力。**
