import os
import json
import logging
import pdb
from typing import List, Optional
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import OpenAI
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .utils.tools import get_current_weather


load_dotenv()

logging.basicConfig(level=logging.INFO)

app = FastAPI(root_path="/api")


def get_required_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


is_azure = bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))

client = OpenAI(
    api_key=get_required_env("AZURE_OPENAI_API_KEY" if is_azure else "OPENAI_API_KEY"),
    base_url=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    default_query={"api-version": "preview"} if is_azure else None,
)

model = (
    get_required_env("AZURE_OPENAI_DEPLOYMENT")
    if is_azure
    else os.environ.get("OPENAI_MODEL", "gpt-4o")
)


class Request(BaseModel):
    id: Optional[str] = None
    messages: List[ClientMessage]


available_tools = {
    "get_current_weather": get_current_weather,
}


def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    # The Vercel AI SDK may send a final, empty API call with the complete
    # conversation history. This is to allow the backend to persist the state.
    # The Azure Mistral API, however, is strict and will reject a history
    # that ends with an assistant message. We intercept this synchronization
    # call and return an empty response to prevent the upstream error.
    if messages and messages[-1]["role"] == "assistant":
        yield ""
        return

    # First API call: Get instructions from the model
    stream = client.chat.completions.create(
        messages=messages,
        model=model,
        stream=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get the current weather at a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {
                                "type": "number",
                                "description": "The latitude of the location",
                            },
                            "longitude": {
                                "type": "number",
                                "description": "The longitude of the location",
                            },
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            }
        ],
    )

    draft_tool_calls = []
    draft_tool_calls_index = -1
    finish_reason = None
    usage = None

    for chunk in stream:
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            if chunk.usage:
                usage = chunk.usage
            continue

        if choice.delta.tool_calls:
            for tool_call in choice.delta.tool_calls:
                if tool_call.function:
                    id = tool_call.id
                    name = tool_call.function.name
                    arguments = tool_call.function.arguments
                    if id is not None:
                        draft_tool_calls_index += 1
                        draft_tool_calls.append(
                            {"id": id, "name": name, "arguments": ""}
                        )
                    if arguments is not None:
                        draft_tool_calls[draft_tool_calls_index][
                            "arguments"
                        ] += arguments

        if choice.delta.content:
            yield "0:{text}\n".format(text=json.dumps(choice.delta.content))

        if choice.finish_reason:
            finish_reason = choice.finish_reason
            if chunk.usage:
                usage = chunk.usage
            break

        if chunk.usage:
            usage = chunk.usage

    # If the model wants to call a tool, execute it and stream the result
    if finish_reason == "tool_calls":
        # Yield the tool call information to the frontend
        for tool_call in draft_tool_calls:
            yield '9:{{"toolCallId":"{id}","toolName":"{name}","args":{args}}}\n'.format(
                id=tool_call["id"],
                name=tool_call["name"],
                args=tool_call["arguments"],
            )

        # Add the assistant's request to the message history
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in draft_tool_calls
                ],
            }
        )

        # Execute the tools and add their results to the message history
        for tool_call in draft_tool_calls:
            tool_result = available_tools[tool_call["name"]](
                **json.loads(tool_call["arguments"])
            )
            yield 'a:{{"toolCallId":"{id}","toolName":"{name}","args":{args},"result":{result}}}\n'.format(
                id=tool_call["id"],
                name=tool_call["name"],
                args=tool_call["arguments"],
                result=json.dumps(tool_result),
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result),
                }
            )

        # Second API call: Get the final response from the model
        second_stream = client.chat.completions.create(
            messages=messages, model=model, stream=True
        )

        final_answer_usage = None
        for chunk in second_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield "0:{text}\n".format(
                    text=json.dumps(chunk.choices[0].delta.content)
                )
            if chunk.usage:
                final_answer_usage = chunk.usage

        if final_answer_usage:
            yield 'e:{{"finishReason":"stop","usage":{{"promptTokens":{prompt},"completionTokens":{completion}}},"isContinued":false}}\n'.format(
                prompt=final_answer_usage.prompt_tokens,
                completion=final_answer_usage.completion_tokens,
            )

    elif finish_reason == "stop":
        # The model finished without calling a tool
        if usage:
            yield 'e:{{"finishReason":"stop","usage":{{"promptTokens":{prompt},"completionTokens":{completion}}},"isContinued":false}}\n'.format(
                prompt=usage.prompt_tokens, completion=usage.completion_tokens
            )


@app.post("/chat")
async def handle_chat_data(request: Request, protocol: str = Query("data")):
    messages = request.messages
    openai_messages = convert_to_openai_messages(messages)

    response = StreamingResponse(stream_text(openai_messages, protocol))
    return response
