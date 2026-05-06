# Python 中 `Protocol` 和 `ABC` 的区别

## 一、先给结论

`Protocol` 和 `ABC` 都可以用来描述“某个对象应该具备什么能力”，但它们的设计目标不同：

| 对比维度 | `Protocol` | `ABC` |
|---|---|---|
| 全称 | `typing.Protocol` | `abc.ABC` |
| 核心思想 | 结构化类型：只要长得像，就算符合 | 名义类型：必须明确继承，才算符合 |
| 主要用途 | 给类型检查器看的接口约束 | 运行时强制子类实现抽象方法 |
| 是否必须继承 | 不必须 | 通常必须继承 |
| 是否影响运行时实例化 | 默认不影响 | 会阻止未实现抽象方法的子类实例化 |
| 适合场景 | 插件、第三方对象、鸭子类型、松耦合接口 | 框架基类、模板方法、强约束继承体系 |
| 检查方式 | 静态类型检查为主，如 mypy、pyright | 运行时检查为主 |

一句话理解：

- `Protocol` 更像“能力描述”：你只要有这些方法和属性，就可以被当成这个类型使用。
- `ABC` 更像“基类契约”：你必须继承我，并实现我规定的方法。

---

## 二、`ABC` 是什么

`ABC` 来自 Python 标准库 `abc`，用于定义抽象基类。

抽象基类可以声明一些必须由子类实现的方法。如果子类没有实现这些抽象方法，就不能被实例化。

```python
from abc import ABC, abstractmethod


class ImageGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """根据 prompt 生成图片 URL"""
        raise NotImplementedError


class NanoBananaImageGenerator(ImageGenerator):
    def generate(self, prompt: str) -> str:
        return f"https://image.example.com/{prompt}"


generator = NanoBananaImageGenerator()
print(generator.generate("一张科技风封面图"))
```

如果子类没有实现 `generate()`：

```python
class BrokenImageGenerator(ImageGenerator):
    pass


generator = BrokenImageGenerator()
```

运行时会报错：

```text
TypeError: Can't instantiate abstract class BrokenImageGenerator with abstract method generate
```

这就是 `ABC` 的核心价值：**在运行时强制子类实现某些方法**。

---

## 三、`Protocol` 是什么

`Protocol` 来自 `typing`，用于定义结构化接口。

它不关心某个类是否继承了自己，只关心这个类是否具备对应的方法和属性。

```python
from typing import Protocol


class ImageGeneratorProtocol(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class NanoBananaClient:
    def generate(self, prompt: str) -> str:
        return f"https://image.example.com/{prompt}"


def create_cover(generator: ImageGeneratorProtocol, title: str) -> str:
    return generator.generate(f"文章封面：{title}")


client = NanoBananaClient()
cover_url = create_cover(client, "AI 如何改变内容创作")
```

注意：`NanoBananaClient` 没有继承 `ImageGeneratorProtocol`，但它有 `generate(prompt: str) -> str` 方法，所以静态类型检查器会认为它符合这个协议。

这就是 `Protocol` 的核心价值：**用结构匹配描述对象能力，减少显式继承带来的耦合**。

---

## 四、名义类型 vs 结构化类型

### 4.1 `ABC`：名义类型

`ABC` 强调“你是谁”。

只有明确继承了某个抽象基类，才属于这个类型体系。

```python
class BaseWriter(ABC):
    @abstractmethod
    def write(self, content: str) -> None:
        raise NotImplementedError


class MarkdownWriter(BaseWriter):
    def write(self, content: str) -> None:
        print(content)
```

这里 `MarkdownWriter` 是 `BaseWriter`，因为它明确继承了 `BaseWriter`。

### 4.2 `Protocol`：结构化类型

`Protocol` 强调“你能做什么”。

只要方法签名匹配，就可以被当成对应类型使用。

```python
class WriterProtocol(Protocol):
    def write(self, content: str) -> None:
        ...


class MarkdownWriter:
    def write(self, content: str) -> None:
        print(content)
```

这里 `MarkdownWriter` 没有继承 `WriterProtocol`，但它有 `write(content: str) -> None`，所以可以被当成 `WriterProtocol` 使用。

---

## 五、具体应用场景

### 场景一：定义框架内部的固定基类，适合用 `ABC`

如果你在写一个框架，希望所有子类都遵循统一生命周期，比如：

- 初始化
- 执行
- 清理

这种场景适合用 `ABC`。

```python
from abc import ABC, abstractmethod


class Agent(ABC):
    @abstractmethod
    async def run(self, state: dict) -> dict:
        raise NotImplementedError


class TitleAgent(Agent):
    async def run(self, state: dict) -> dict:
        state["titles"] = ["标题 A", "标题 B"]
        return state
```

适用原因：

- 你控制所有子类的实现。
- 希望子类必须继承统一基类。
- 希望运行时阻止未完成实现的子类被实例化。
- 后续可以在基类中加入通用逻辑，如日志、异常处理、模板方法。

---

### 场景二：适配第三方 SDK，适合用 `Protocol`

假设你有多个 LLM 客户端：

- DashScope 客户端
- OpenAI 客户端
- 自研模型客户端

这些客户端可能来自不同 SDK，不方便也不应该让它们继承你的基类。

这时适合用 `Protocol`。

```python
from typing import Protocol


class ChatClient(Protocol):
    async def chat(self, prompt: str) -> str:
        ...


class DashScopeClient:
    async def chat(self, prompt: str) -> str:
        return "DashScope response"


class OpenAIClient:
    async def chat(self, prompt: str) -> str:
        return "OpenAI response"


async def generate_article(client: ChatClient, topic: str) -> str:
    return await client.chat(f"请写一篇关于 {topic} 的文章")
```

适用原因：

- 不要求第三方类继承你的基类。
- 只关心对象有没有 `chat()` 能力。
- 对测试替身、mock 对象、不同 SDK 适配很友好。
- 可以降低业务代码对具体实现的依赖。

---

### 场景三：插件系统，适合用 `Protocol`

插件系统通常只要求插件具备某些方法，而不希望插件作者被迫继承某个基类。

```python
from typing import Protocol


class ImagePlugin(Protocol):
    name: str

    def generate(self, prompt: str) -> str:
        ...


class PexelsPlugin:
    name = "pexels"

    def generate(self, prompt: str) -> str:
        return f"https://pexels.example.com/search?q={prompt}"


class SvgDiagramPlugin:
    name = "svg_diagram"

    def generate(self, prompt: str) -> str:
        return f"<svg><!-- {prompt} --></svg>"


def use_plugin(plugin: ImagePlugin, prompt: str) -> str:
    return plugin.generate(prompt)
```

适用原因：

- 插件只要满足接口形状即可。
- 插件作者不需要依赖你的基础包。
- 系统更开放，扩展成本更低。

---

### 场景四：需要复用通用代码，适合用 `ABC`

如果基类不仅声明接口，还要提供通用逻辑，那么 `ABC` 更合适。

```python
from abc import ABC, abstractmethod


class BaseRetriever(ABC):
    def retrieve_and_format(self, query: str) -> str:
        chunks = self.retrieve(query)
        return "\n\n".join(chunks)

    @abstractmethod
    def retrieve(self, query: str) -> list[str]:
        raise NotImplementedError


class QdrantRetriever(BaseRetriever):
    def retrieve(self, query: str) -> list[str]:
        return ["chunk 1", "chunk 2"]
```

这里 `BaseRetriever` 不只是一个接口，它还提供了 `retrieve_and_format()` 的通用流程。

适用原因：

- 基类有可复用逻辑。
- 子类只需要填充其中一部分行为。
- 适合模板方法模式。

---

### 场景五：单元测试和 Mock，适合用 `Protocol`

业务函数只依赖协议，不依赖具体实现，测试时可以轻松传入假对象。

```python
from typing import Protocol


class ArticleRepository(Protocol):
    def save(self, title: str, content: str) -> int:
        ...


class FakeArticleRepository:
    def save(self, title: str, content: str) -> int:
        return 1


def create_article(repo: ArticleRepository, title: str, content: str) -> int:
    return repo.save(title, content)


def test_create_article() -> None:
    repo = FakeArticleRepository()
    article_id = create_article(repo, "测试标题", "测试正文")
    assert article_id == 1
```

适用原因：

- 测试替身不需要继承任何类。
- 业务代码只依赖接口能力。
- 更符合依赖倒置原则。

---

## 六、`Protocol` 能不能做运行时检查

可以，但需要加 `@runtime_checkable`。

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Runnable(Protocol):
    def run(self) -> None:
        ...


class Task:
    def run(self) -> None:
        print("running")


task = Task()
print(isinstance(task, Runnable))  # True
```

但要注意：运行时检查只能粗略检查属性或方法是否存在，不能完整检查参数类型、返回值类型。

例如它大致能判断有没有 `run`，但不能严格判断 `run()` 的签名是否完全正确。

所以 `Protocol` 的主要价值仍然是配合静态类型检查器，而不是替代 `ABC` 的运行时强约束。

---

## 七、怎么选择

### 优先选择 `Protocol` 的情况

- 只想描述对象能力，不想要求继承。
- 需要适配第三方类、SDK 类、已有类。
- 希望降低模块之间的耦合。
- 希望测试时能轻松传入 fake/mock 对象。
- 项目重视类型提示和静态类型检查。

### 优先选择 `ABC` 的情况

- 你正在设计一个明确的继承体系。
- 希望运行时强制子类实现某些方法。
- 基类中有通用方法、模板流程或共享状态。
- 子类都由你自己控制。
- 未实现抽象方法时，希望程序尽早报错。

---

## 八、实践建议

在现代 Python 项目中，可以这样取舍：

| 需求 | 推荐 |
|---|---|
| 只定义接口形状 | `Protocol` |
| 适配外部对象 | `Protocol` |
| 依赖注入参数类型 | `Protocol` |
| 插件扩展点 | `Protocol` |
| 框架内部基类 | `ABC` |
| 需要共享通用逻辑 | `ABC` |
| 需要运行时阻止错误实现 | `ABC` |

一个实用原则：

> 对外部依赖和业务边界，用 `Protocol` 保持松耦合；对内部框架和稳定继承体系，用 `ABC` 保持强约束。

---

## 九、放到当前项目中的理解

以当前文章创作系统为例：

- 如果要定义 “LLM 客户端必须能 chat” 这种能力，适合用 `Protocol`。
- 如果要定义 “所有 Agent 都必须实现 run，并且共享日志、状态更新、异常处理流程”，适合用 `ABC`。
- 如果要定义 “图片生成插件只要有 generate 方法即可接入”，适合用 `Protocol`。
- 如果要定义 “所有 Retriever 都继承统一基类，并复用 context packing 流程”，适合用 `ABC`。

示例：

```python
from abc import ABC, abstractmethod
from typing import Protocol


class LLMClient(Protocol):
    async def chat(self, prompt: str) -> str:
        ...


class BaseAgent(ABC):
    async def execute(self, state: dict) -> dict:
        self.before_run(state)
        result = await self.run(state)
        self.after_run(result)
        return result

    def before_run(self, state: dict) -> None:
        pass

    def after_run(self, state: dict) -> None:
        pass

    @abstractmethod
    async def run(self, state: dict) -> dict:
        raise NotImplementedError
```

这里：

- `LLMClient` 用 `Protocol`，因为业务只关心客户端有没有 `chat()`。
- `BaseAgent` 用 `ABC`，因为它有固定执行流程，并且要求子类实现 `run()`。

