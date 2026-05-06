# `schemas/article.py` 解析笔记

## 一、文件核心作用

`article.py` 是整个文章生成系统的**数据契约层**，承担三大职责：

| 职责 | 说明 |
|---|---|
| **请求/响应模型** | 定义 API 接口的输入输出格式，FastAPI 自动完成校验和序列化 |
| **内部状态载体** | `ArticleState` 是多 Agent 之间传递数据的共享对象 |
| **数据结构规范** | 约束各 Agent 产出物的字段类型，避免运行时类型错误 |

---

## 二、文件结构总览

```
article.py
├── API 请求模型（Request）
│   ├── ArticleCreateRequest       # 创建文章
│   ├── ArticleQueryRequest        # 查询文章（含分页）
│   ├── ArticleConfirmTitleRequest # 用户确认标题
│   ├── ArticleConfirmOutlineRequest # 用户确认大纲
│   └── ArticleAiModifyOutlineRequest # AI 修改大纲
│
├── API 响应模型（VO）
│   └── ArticleVO                  # 文章视图对象（返回给前端）
│
├── Agent 中间数据模型
│   ├── TitleOption                # Agent1 产出：标题候选项
│   ├── TitleResult                # 用户选定的标题
│   ├── OutlineSection             # 大纲单个章节
│   ├── OutlineResult              # Agent2 产出：完整大纲
│   ├── ImageRequirement           # Agent4 产出：单张配图需求
│   ├── ImageResult                # Agent5 产出：单张配图结果
│   └── Agent4Result               # Agent4 完整返回（正文+配图需求）
│
└── 状态对象（State）
    └── ArticleState               # 多 Agent 共享状态（非 Pydantic）
```

---

## 三、关键设计解析

### 3.1 `ArticleState`：为什么不继承 `BaseModel`？

```python
class ArticleState:
    """文章生成状态（智能体间共享的状态对象）"""
    def __init__(self):
        self.task_id: Optional[str] = None
        self.title_options: Optional[List[TitleOption]] = None
        self.outline: Optional[OutlineResult] = None
        # ...
```

**原因分析：**

- `ArticleState` 是运行时的**可变状态容器**，需要在多个 Agent 执行过程中被反复读写。
- Pydantic `BaseModel` 默认不可变（immutable）、会做类型校验，不适合作为频繁修改的状态对象。
- 选用普通 Python class，赋值更灵活、性能更高，Agent 每步直接写入即可。

**设计模式：** 这是经典的**黑板模式（Blackboard Pattern）**，所有 Agent 共享同一块"黑板"读写数据。

---

### 3.2 `alias` + `populate_by_name`：前后端字段命名桥梁

```python
class TitleOption(BaseModel):
    main_title: str = Field(..., alias="mainTitle")
    sub_title: str = Field(..., alias="subTitle")

    class Config:
        populate_by_name = True
```

- **Python 惯例**：变量名用 `snake_case`（`main_title`）
- **JSON/前端惯例**：字段名用 `camelCase`（`mainTitle`）
- `alias="mainTitle"`：接收前端 JSON 时用 `mainTitle` 解析，序列化返回时也输出 `mainTitle`
- `populate_by_name = True`：允许在 Python 代码内部同时用 `main_title` 赋值，不强制必须用别名

---

### 3.3 `Field` 的三种常见用法

```python
# 必填字段 + 别名
task_id: str = Field(..., alias="taskId", min_length=1)

# 可选字段 + 默认值
style: Optional[str] = Field(None, description="文章风格")

# 有默认值的字段
prompt: str = Field(default="", description="AI 生图提示词")
```

| 写法 | 含义 |
|---|---|
| `Field(...)` | 必填，没有默认值（`...` 是 Pydantic 约定的"必填"标记）|
| `Field(None)` | 可选，默认为 `None` |
| `Field(default="")` | 有默认值 |
| `min_length=1` | 内置校验器，字符串长度不得小于 1 |

---

### 3.4 `ArticleVO`：视图对象的职责

`VO（View Object）` 是专门面向前端返回的数据结构，与数据库 Model 分离：

```python
class ArticleVO(BaseModel):
    id: int
    task_id: str = Field(..., alias="taskId")
    # 包含了所有前端需要展示的字段
    outline: Optional[List[Any]] = None   # Any：大纲结构灵活
    images: Optional[List[Any]] = None    # Any：图片结构灵活
```

**为什么用 `Any`？**  
大纲和图片的结构可能随业务版本演进，用 `Any` 保留灵活性，避免 VO 频繁改动。

---

### 3.5 `Agent4Result`：组合模式

```python
class Agent4Result(BaseModel):
    content_with_placeholders: str = Field(..., alias="contentWithPlaceholders")
    image_requirements: List[ImageRequirement] = Field(..., alias="imageRequirements")
```

Agent4 同时返回两样东西：
1. 插入了占位符的正文（如 `{{IMAGE_PLACEHOLDER_1}}`）
2. 每个占位符对应的配图需求列表

这两者强绑定，用一个 Model 包装，保证原子性解析，避免漏字段。

---

## 四、面试常考问题

### Q1：Pydantic `BaseModel` 和普通 Python `dataclass` 有什么区别？

| 对比项 | Pydantic BaseModel | dataclass |
|---|---|---|
| 类型校验 | 运行时自动校验 | 不校验（仅类型注解） |
| JSON 序列化 | 内置 `.model_dump()` / `.model_dump_json()` | 需手动或借助第三方库 |
| 别名支持 | `Field(alias=...)` 原生支持 | 不支持 |
| 默认值校验 | 支持 `min_length`、`gt`、`regex` 等 | 不支持 |
| 性能 | 相对较慢（有校验开销） | 更快 |
| 适用场景 | API 数据校验、序列化 | 轻量内部数据容器 |

---

### Q2：`Field(...)` 中的 `...` 是什么意思？

`...` 是 Python 内置的 `Ellipsis` 对象，在 Pydantic 中作为**必填字段**的标记。等价于"该字段没有默认值，调用方必须传入"。

```python
# 这两种写法等价
name: str = Field(...)
name: str  # 不写 Field 时，Pydantic 也会视为必填
```

---

### Q3：`Optional[str]` 和 `str = None` 有什么区别？

```python
# 写法一：类型注解层面允许 None，但 Pydantic 仍视为必填
style: Optional[str]

# 写法二：有默认值 None，Pydantic 视为可选字段（推荐）
style: Optional[str] = None
```

在 **Pydantic v2** 中，`Optional[str]` 不再自动隐含默认值为 `None`，必须显式写 `= None` 才是可选字段。

---

### Q4：`populate_by_name = True` 的作用是什么？

当一个字段设置了 `alias` 后，默认 Pydantic **只能通过别名赋值**。

```python
class TitleOption(BaseModel):
    main_title: str = Field(..., alias="mainTitle")

# 不加 populate_by_name=True：
TitleOption(mainTitle="标题")   # ✅ 正常
TitleOption(main_title="标题")  # ❌ 报错

# 加了 populate_by_name=True：
TitleOption(main_title="标题")  # ✅ 也能用
```

实际项目中，Python 内部代码更习惯用 `snake_case`，所以通常都要开启此选项。

---

### Q5：Pydantic v1 的 `class Config` 和 v2 的 `model_config` 有什么区别？

```python
# Pydantic v1 写法（本项目使用）
class Config:
    populate_by_name = True

# Pydantic v2 推荐写法
from pydantic import ConfigDict
model_config = ConfigDict(populate_by_name=True)
```

两者功能相同，`class Config` 是 v1 遗留写法，v2 兼容但推荐迁移到 `model_config`。

---

### Q6：FastAPI 如何利用这些 `BaseModel` 自动完成校验？

```python
@router.post("/article")
async def create_article(request: ArticleCreateRequest):
    # FastAPI 在此之前已完成：
    # 1. 解析请求 Body 的 JSON
    # 2. 按 ArticleCreateRequest 字段做类型校验
    # 3. 校验 topic 的 min_length=1
    # 4. 如果校验失败，自动返回 422 Unprocessable Entity
    pass
```

FastAPI 依赖 Pydantic 的 `__get_validators__` 机制，在路由函数执行前完成所有校验，开发者无需手动写 `if not request.topic` 这类代码。

---

### Q7：Schema 层和 Model 层为什么要分离？

| 层 | 文件位置 | 职责 |
|---|---|---|
| Schema | `app/schemas/` | 定义 API 的输入输出结构，面向网络传输 |
| Model | `app/models/` | 定义数据库表结构，面向持久化存储 |

**原因：**
1. 数据库字段和 API 字段不一定一一对应（如密码字段不能返回给前端）
2. 同一张表可能有多个不同的响应视图（列表简略版 vs 详情完整版）
3. 解耦后，数据库结构变化不会直接影响 API 契约

---

### Q8：`model_dump(by_alias=True)` 和 `model_dump()` 有什么区别？

```python
option = TitleOption(mainTitle="AI 时代", subTitle="副标题")

option.model_dump()
# {'main_title': 'AI 时代', 'sub_title': '副标题'}  # Python 字段名

option.model_dump(by_alias=True)
# {'mainTitle': 'AI 时代', 'subTitle': '副标题'}  # 别名（camelCase）
```

返回给前端时应使用 `by_alias=True`，保证 JSON 格式符合前端约定。

---

## 五、知识点速记卡

```
Field(...)          → 必填字段
Field(None)         → 可选字段
Field(alias="xxx")  → JSON 字段名映射
min_length=1        → 最小长度校验

populate_by_name=True → 允许用 Python 名赋值
model_dump()          → 序列化为 dict（Python 名）
model_dump(by_alias=True) → 序列化为 dict（别名）

ArticleState（普通 class）→ 可变状态，Agent 间共享
BaseModel（Pydantic）   → 不可变校验模型，用于 I/O

Schema 层 → 面向网络，约束 API 格式
Model 层  → 面向数据库，约束存储结构
```
