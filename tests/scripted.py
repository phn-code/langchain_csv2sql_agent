from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field


class ScriptedModel(BaseChatModel):
    """Replies from a script: a pydantic object answers a structured-output call, a string answers a plain one."""

    script: list[BaseModel | str]
    prompts: list[str] = Field(default_factory=list[str])

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.prompts.append(str(messages[-1].content))
        if not self.script:
            raise AssertionError("ScriptedModel ran out of replies")
        reply = self.script.pop(0)
        if isinstance(reply, BaseModel):
            call = {"name": type(reply).__name__, "args": reply.model_dump(), "id": f"call_{len(self.prompts)}"}
            message = AIMessage(content="", tool_calls=[call])
        else:
            message = AIMessage(content=reply)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # type: ignore[override]
        return self
