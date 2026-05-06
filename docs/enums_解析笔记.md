# `models/enums.py` 解析笔记

## 一、文件核心作用

`enums.py` 是整个系统的**常量中枢**，将所有业务中会反复出现的"固定取值集合"统一用枚举管理，避免在代码各处散落魔法字符串（Magic String）。

**核心价值：**
- 类型安全：IDE 可以自动补全，写错枚举值编译阶段即可发现
- 单一来源：修改某个取值只需改一处，不会遗漏
- 可扩展：在枚举类上挂载业务方法，集中内聚相关逻辑

所有枚举均继承 `(str, Enum)`，这意味着枚举值本身就是字符串，可直接写入数据库、序列化 JSON，无需额外转换。

---

## 二、各枚举类逐一解析

---

### 2.1 `ArticleStatusEnum` — 文章粗粒度状态

```python
class ArticleStatusEnum(str, Enum):
    PENDING = "PENDING"       # 待处理（刚创建）
    PROCESSING = "PROCESSING" # AI 正在生成中
    COMPLETED = "COMPLETED"   # 全部完成
    FAILED = "FAILED"         # 生成失败
```

**作用：** 记录文章整体的生命周期状态，存储在数据库 `articles` 表，前端据此判断是否显示"生成中"进度条或"失败"提示。

**与 `ArticlePhaseEnum` 的关系：**

```
ArticleStatusEnum（粗粒度）
└── PROCESSING
    ├── TITLE_GENERATING   ─┐
    ├── TITLE_SELECTING     │
    ├── OUTLINE_GENERATING  │ ArticlePhaseEnum（细粒度）
    ├── OUTLINE_EDITING     │
    └── CONTENT_GENERATING ─┘
```

Status 是"有没有在跑"，Phase 是"跑到哪一步了"。

---

### 2.2 `ArticlePhaseEnum` — 文章细粒度阶段（含状态机）

```python
class ArticlePhaseEnum(str, Enum):
    PENDING             = "PENDING"             # 初始状态
    TITLE_GENERATING    = "TITLE_GENERATING"    # Agent1 正在生成标题
    TITLE_SELECTING     = "TITLE_SELECTING"     # 等待用户选择标题
    OUTLINE_GENERATING  = "OUTLINE_GENERATING"  # Agent2 正在生成大纲
    OUTLINE_EDITING     = "OUTLINE_EDITING"     # 等待用户编辑/确认大纲
    CONTENT_GENERATING  = "CONTENT_GENERATING"  # Agent3~5 正在生成正文和配图
```

**核心方法：`can_transition_to()`**

```python
def can_transition_to(self, target_phase: "ArticlePhaseEnum") -> bool:
    transitions = {
        PENDING:             {TITLE_GENERATING},
        TITLE_GENERATING:    {TITLE_SELECTING},
        TITLE_SELECTING:     {OUTLINE_GENERATING},
        OUTLINE_GENERATING:  {OUTLINE_EDITING},
        OUTLINE_EDITING:     {CONTENT_GENERATING},
        CONTENT_GENERATING:  set(),   # 终态，无法再流转
    }
    return target_phase in transitions.get(self, set())
```

**设计亮点：这是一个内嵌在枚举中的有限状态机（FSM）。**

```
PENDING
  ↓
TITLE_GENERATING → TITLE_SELECTING
                         ↓
               OUTLINE_GENERATING → OUTLINE_EDITING
                                          ↓
                               CONTENT_GENERATING（终态）
```

每次 Phase 流转前调用 `can_transition_to()` 进行合法性检查，防止乱序执行（如跳过标题选择直接生成大纲）。

---

### 2.3 `ArticleStyleEnum` — 文章写作风格

```python
class ArticleStyleEnum(str, Enum):
    TECH        = "tech"        # 科技/专业风格
    EMOTIONAL   = "emotional"   # 情感/共鸣风格
    EDUCATIONAL = "educational" # 知识/教学风格
    HUMOROUS    = "humorous"    # 幽默/轻松风格
```

**作用：** 用户创建文章时选择风格，系统据此在 Prompt 末尾附加不同的风格引导语（`PromptConstant.STYLE_*_PROMPT`），影响 LLM 的输出语气和用词。

**核心方法：`is_valid()`**

```python
@classmethod
def is_valid(cls, value: Optional[str]) -> bool:
    if not value:
        return True  # 允许不选风格
    return value in [e.value for e in cls]
```

用于在接收前端参数时做校验。注意：**空值视为合法**（用户可以不指定风格）。

---

### 2.4 `ImageMethodEnum` — 配图获取方式

```python
class ImageMethodEnum(str, Enum):
    PEXELS      = "PEXELS"      # 真实图库检索（Pexels API）
    NANO_BANANA = "NANO_BANANA" # AI 生图（NanoBanana API）
    MERMAID     = "MERMAID"     # 代码生成结构图（Mermaid）
    ICONIFY     = "ICONIFY"     # 图标库检索
    EMOJI_PACK  = "EMOJI_PACK"  # 表情包检索
    SVG_DIAGRAM = "SVG_DIAGRAM" # AI 生成 SVG 概念示意图
    PICSUM      = "PICSUM"      # 随机占位图（降级兜底）
```

**配图方式分类：**

| 类别 | 枚举值 |
|---|---|
| 图库检索 | `PEXELS`、`ICONIFY`、`EMOJI_PACK` |
| AI 生成 | `NANO_BANANA`、`MERMAID`、`SVG_DIAGRAM` |
| 降级兜底 | `PICSUM` |

**核心方法：**

```python
def is_ai_generated(self) -> bool:
    """是否为 AI 生图方式（NANO_BANANA / MERMAID / SVG_DIAGRAM）"""

def is_fallback(self) -> bool:
    """是否为降级方案（PICSUM，其他全部失败时使用）"""

@classmethod
def get_default_search_method(cls):  # → PEXELS
def get_default_ai_method(cls):      # → NANO_BANANA
def get_fallback_method(cls):        # → PICSUM
```

**降级策略：** 当所有配图方式都失败时，自动回退到 `PICSUM`（返回随机图片），保证文章生成流程不因配图失败而中断。

---

### 2.5 `SseMessageTypeEnum` — SSE 推送消息类型

```python
class SseMessageTypeEnum(str, Enum):
    AGENT1_COMPLETE   = "AGENT1_COMPLETE"   # Agent1 完成（生成标题）
    TITLES_GENERATED  = "TITLES_GENERATED"  # 标题方案已就绪，等待用户选择
    AGENT2_STREAMING  = "AGENT2_STREAMING"  # Agent2 流式输出（大纲字符流）
    AGENT2_COMPLETE   = "AGENT2_COMPLETE"   # Agent2 完成
    OUTLINE_GENERATED = "OUTLINE_GENERATED" # 大纲已就绪，等待用户编辑
    AGENT3_STREAMING  = "AGENT3_STREAMING"  # Agent3 流式输出（正文字符流）
    AGENT3_COMPLETE   = "AGENT3_COMPLETE"   # Agent3 完成
    AGENT4_COMPLETE   = "AGENT4_COMPLETE"   # Agent4 完成（配图需求分析）
    IMAGE_COMPLETE    = "IMAGE_COMPLETE"    # 单张配图生成完成
    AGENT5_COMPLETE   = "AGENT5_COMPLETE"   # Agent5 完成（所有配图）
    MERGE_COMPLETE    = "MERGE_COMPLETE"    # 图文合成完成
    ALL_COMPLETE      = "ALL_COMPLETE"      # 全部流程完成
    ERROR             = "ERROR"             # 任意阶段发生错误
```

**作用：** 前端通过 SSE 长连接持续接收消息，通过 `type` 字段区分当前推送的是什么内容，从而更新不同的 UI 状态。

**核心方法：`get_streaming_prefix()`**

```python
def get_streaming_prefix(self) -> str:
    return f"{self.value}:"
# 例：AGENT2_STREAMING.get_streaming_prefix() → "AGENT2_STREAMING:"
```

流式消息在传输时格式为 `"类型前缀:内容片段"`，前缀作为分隔符让消费方知道这段字符属于哪个 Agent 的输出。

**完整消息流时序：**

```
前端                            后端（SSE 推送）
 |                               |
 |←── TITLES_GENERATED ──────────| Agent1 完成
 | [用户选择标题]                 |
 |←── AGENT2_STREAMING:第一章... | Agent2 流式输出大纲（逐 token）
 |←── AGENT2_STREAMING:第二章... |
 |←── OUTLINE_GENERATED ─────────| 大纲完整，等待用户
 | [用户确认大纲]                 |
 |←── AGENT3_STREAMING:正文内容  | Agent3 流式输出正文
 |←── IMAGE_COMPLETE:{...} ──────| 第1张图完成
 |←── IMAGE_COMPLETE:{...} ──────| 第2张图完成
 |←── ALL_COMPLETE ──────────────| 全部结束
```

---

### 2.6 `PaymentStatusEnum` — 支付状态

```python
class PaymentStatusEnum(str, Enum):
    PENDING   = "PENDING"   # 待支付（订单已创建，未付款）
    SUCCEEDED = "SUCCEEDED" # 支付成功
    FAILED    = "FAILED"    # 支付失败
    REFUNDED  = "REFUNDED"  # 已退款
```

**作用：** 对应支付宝/微信支付回调的订单状态，存储在 `payments` 表，用于幂等判断（防止重复处理同一笔支付回调）。

---

### 2.7 `ProductTypeEnum` — 产品类型（含价格和描述）

```python
class ProductTypeEnum(str, Enum):
    VIP_PERMANENT = "VIP_PERMANENT"  # 永久会员（目前唯一产品）

    @property
    def description(self) -> str:
        return {"VIP_PERMANENT": "永久会员"}[self]

    @property
    def price(self) -> Decimal:
        return {"VIP_PERMANENT": Decimal("199.00")}[self]
```

**设计亮点：** 将产品的描述文案和价格作为 `@property` 直接挂载在枚举上，代码中用 `ProductTypeEnum.VIP_PERMANENT.price` 即可取到价格，无需额外查表或硬编码。

**使用 `Decimal` 而非 `float` 的原因：** 浮点数在计算时会有精度误差（如 `0.1 + 0.2 ≠ 0.3`），金融/支付场景必须使用 `Decimal` 保证精确计算。

---

## 三、设计模式总结

### `(str, Enum)` 多重继承

```python
class ArticleStatusEnum(str, Enum):
    PENDING = "PENDING"
```

枚举值同时是字符串，因此：
- 存入数据库：直接存 `"PENDING"`，无需 `.value`
- FastAPI 序列化：直接输出字符串，无需额外处理
- 比较：`status == "PENDING"` 和 `status == ArticleStatusEnum.PENDING` 均成立

### 枚举挂载业务方法

本文件中三种挂载方式：

| 方式 | 枚举 | 示例 |
|---|---|---|
| 实例方法 | `ArticlePhaseEnum` | `phase.can_transition_to(target)` |
| 类方法 `@classmethod` | `ImageMethodEnum` | `ImageMethodEnum.get_fallback_method()` |
| 属性 `@property` | `ProductTypeEnum` | `product.price` |

将业务逻辑内聚到枚举本身，是"**富枚举（Rich Enum）**"模式，避免在 Service 层到处写 `if method == "PICSUM"` 这类判断。

---

## 四、面试常考问题

### Q1：Python 中 `(str, Enum)` 多重继承的作用？

继承 `str` 后，枚举成员本身就是字符串，可以直接用于字符串比较、JSON 序列化、数据库写入，不需要手动调用 `.value`。

```python
status = ArticleStatusEnum.PENDING
status == "PENDING"   # True
json.dumps(status)    # '"PENDING"'
```

### Q2：为什么支付金额用 `Decimal` 而不用 `float`？

`float` 是 IEEE 754 浮点数，存在二进制精度问题，例如：
```python
0.1 + 0.2 == 0.3  # False！结果是 0.30000000000000004
```
`Decimal` 使用十进制精确运算，适合金融场景：
```python
Decimal("0.1") + Decimal("0.2") == Decimal("0.3")  # True
```

### Q3：`ArticlePhaseEnum.can_transition_to()` 体现了什么设计模式？

**有限状态机（Finite State Machine，FSM）**。用字典定义合法流转关系，每次状态变更前校验，防止非法跳转（如用户绕过标题选择直接触发大纲生成）。

### Q4：枚举挂载方法（富枚举）和普通工具函数相比有什么优势？

| 对比项 | 富枚举 | 工具函数 |
|---|---|---|
| 内聚性 | 逻辑和数据放在一起 | 逻辑分散在别处 |
| 调用方式 | `method.is_fallback()` | `is_fallback(method)` |
| 可发现性 | IDE 输入 `.` 即可提示 | 需要知道函数在哪 |
| 扩展性 | 新增枚举值时容易忘记更新 | 同样问题 |

### Q5：`@classmethod` 和 `@property` 在枚举中分别适合什么场景？

- `@classmethod`：与某个具体枚举值无关，返回的是整个枚举类的某个"默认成员"，如 `get_fallback_method()` 返回 `PICSUM`
- `@property`：每个枚举值有自己独立的属性值，如每个 `ProductTypeEnum` 成员有自己的 `price` 和 `description`
