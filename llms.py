from dataclasses import dataclass
from typing import Any


@dataclass
class FunctionCall:
    """一次工具函数调用。"""

    name: str
    arguments: str  # JSON 字符串

    def model_dump(self) -> dict:
        return {"name": self.name, "arguments": self.arguments}


@dataclass
class ToolCall:
    """一次 tool_call 项，用于组装 ChatResponse.tool_calls。"""

    id: str
    function: FunctionCall
    type: str = "function"

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "function": self.function.model_dump(),
        }


@dataclass
class ChatResponse:
    """`model.chat()` 的统一返回对象。

    字段全部按最宽松形式定义，调用方使用 getattr / if ... else 做兜底，
    以便在接入不同后端时保持一致的读取方式。
    """

    role: str = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    reasoning_content: str = ""
    reasoning_details: Any = None


# ---------------------------------------------------------------------------
# Base contract
# ---------------------------------------------------------------------------


class BaseModel:
    """所有模型接入的基类。子类必须实现 :meth:`chat`。"""

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_new_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """发起一次对话。

        Parameters
        ----------
        messages : list[dict]
            形如 ``[{"role": "user", "content": "hi"}, ...]``。
        tools : list[dict], optional
            形如 ``[{"type": "function", "function": {"name": ..., ...}}, ...]``。
        temperature / top_p / max_new_tokens : float | int | None, optional
            采样参数。具体实现可以选择性支持。
        **kwargs : Any
            其他未识别参数，子类可以按需忽略或使用。
        """
        raise NotImplementedError("subclass must implement chat()")
