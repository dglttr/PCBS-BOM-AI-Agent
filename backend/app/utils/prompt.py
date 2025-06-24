import json
from enum import Enum
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel, Field
import base64
from typing import List, Optional, Any
from .attachment import ClientAttachment

class ToolInvocationState(str, Enum):
    CALL = 'call'
    PARTIAL_CALL = 'partial-call'
    RESULT = 'result'

class ToolInvocation(BaseModel):
    toolCallId: str
    toolName: str
    args: Any
    result: Any
    state: Optional[str] = None
    step: Optional[int] = None


class FunctionCall(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: str
    function: FunctionCall


class ClientMessage(BaseModel):
    role: str
    content: str
    id: Optional[str] = None
    createdAt: Optional[Any] = None
    toolInvocations: Optional[List[ToolInvocation]] = Field(default=None)


def convert_to_openai_messages(
    messages: List[ClientMessage],
) -> List[ChatCompletionMessageParam]:
    # This function translates the Vercel AI SDK's message format into the format
    # expected by the OpenAI API.
    #
    # WHY: The Vercel AI SDK is designed to provide a rich, interactive frontend
    # experience that is independent of the specific AI provider. To do this, it
    # exposes the AI's "thought process" to the client. After a tool call, it
    # bundles the entire history of that turn (the tool call request, the tool
    # result, and the final text answer) into a single, complex assistant message.
    # This allows the frontend to render intermediate states, like "Calling the
    # weather tool... 🌦️", instead of just a generic loading spinner.
    #
    # THE PROBLEM: This bundled format is not what the OpenAI API expects. The
    # API requires an explicit, multi-step dialogue for tool calls:
    # 1. An assistant message with a `tool_calls` object.
    # 2. A `tool` message with the result for each tool call.
    # 3. A final assistant message with the text content.
    #
    # THE SOLUTION: This function acts as a translator. It "un-bundles" the
    # Vercel SDK's rich format back into the strict, multi-step dialogue that
    # the OpenAI API understands.
    openai_messages: List[ChatCompletionMessageParam] = []

    for message in messages:
        if message.role == "user":
            openai_messages.append({"role": "user", "content": message.content})
        elif message.role == "assistant":
            if message.toolInvocations:
                openai_messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": ti.toolCallId,
                                "type": "function",
                                "function": {
                                    "name": ti.toolName,
                                    "arguments": json.dumps(ti.args),
                                },
                            }
                            for ti in message.toolInvocations
                        ],
                    }
                )
                for ti in message.toolInvocations:
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": ti.toolCallId,
                            "content": json.dumps(ti.result),
                        }
                    )
                if message.content:
                    openai_messages.append(
                        {"role": "assistant", "content": message.content}
                    )
            else:
                openai_messages.append(
                    {"role": "assistant", "content": message.content}
                )

    return openai_messages
