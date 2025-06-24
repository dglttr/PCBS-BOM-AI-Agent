import os
import json
import logging
import asyncio
from typing import List, Optional
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .utils.tools import get_current_weather
from .bom.router import router as bom_router
from .bom.tools import process_and_enrich_bom
import httpx


load_dotenv()

logging.basicConfig(level=logging.INFO)

app = FastAPI(root_path="/api")
app.include_router(bom_router)

client = AsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

model = "gemini-2.5-flash-preview-05-20"


class Request(BaseModel):
    id: Optional[str] = None
    messages: List[ClientMessage]


available_tools = {
    "get_current_weather": get_current_weather,
    "process_and_enrich_bom": process_and_enrich_bom,
}

master_prompt = """
You are a helpful and conversational BOM Analyst assistant.
Your goal is to help the user process a Bill of Materials (BOM) file.

Here is the flow:
1.  When the user uploads a file, they will provide a `job_id`.
2.  Your first job is to understand the user's project requirements. You MUST ask clarifying questions to determine key assumptions before processing the file. Essential assumptions to ask for are:
    - The industry for the project (e.g., Automotive, Consumer Electronics, Medical). This affects component standards.
    - The total order quantity. This is crucial for cost analysis.
    - Any critical performance requirements (e.g., temperature ranges, specific tolerances).
3.  Engage in a natural conversation to get these assumptions. Do NOT ask for them all in one go. Ask one question at a time.
4.  Once you are confident you have the necessary assumptions, you MUST call the `process_and_enrich_bom` tool. You must pass both the `job_id` from the user's first message and the collected `assumptions` dictionary as arguments to this tool.
5.  After the tool returns the structured JSON data, your final job is to present this information to the user in a clear, user-friendly way. Do not just dump the raw JSON. Summarize the findings, mention how many parts were parsed, and perhaps highlight any potential issues found. Present the structured data in a user-friendly format.
"""

async def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    # This generator function now handles the full tool-calling agent loop.
    
    # Prepend the master prompt to the conversation
    conversation_history: List[ChatCompletionMessageParam] = [{"role": "system", "content": master_prompt}]
    conversation_history.extend(messages)

    # First API call: Get instructions from the model
    logging.info("Agent loop started. Waiting for LLM response...")
    stream = await client.chat.completions.create(
        messages=conversation_history,
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
                            "latitude": {"type": "number"},
                            "longitude": {"type": "number"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "process_and_enrich_bom",
                    "description": "Processes a BOM file to parse its structure and enrich it with supplier data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "The unique ID of the BOM file processing job, obtained from the initial user message.",
                            },
                            "assumptions": {
                                "type": "object",
                                "description": "A dictionary of user-provided assumptions, like industry and quantity.",
                            }
                        },
                        "required": ["job_id", "assumptions"],
                    },
                },
            }
        ],
    )

    # --- Step 1: Handle Streaming Text and Tool Calls ---
    tool_calls = []
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield f"0:{json.dumps(delta.content)}\n"
        
        if delta.tool_calls:
            # Append tool call chunks to a list
            if not tool_calls:
                # The first chunk has the full tool call structure
                for tc in delta.tool_calls:
                    if tc.function:
                        tool_calls.append({"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments or ""}})
            else:
                # Subsequent chunks only have argument diffs
                for i, tc in enumerate(delta.tool_calls):
                    if tc.function and tc.function.arguments:
                        tool_calls[i]["function"]["arguments"] += tc.function.arguments

    # --- Step 2: If the model decided to call a tool, execute it ---
    if tool_calls:
        logging.info(f"LLM decided to call {len(tool_calls)} tool(s).")
        # Add the assistant's tool call message to the history
        conversation_history.append({"role": "assistant", "tool_calls": tool_calls})

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            # Execute the tool
            logging.info(f"Executing tool: {tool_name} with args: {tool_args}")
            tool_function = available_tools.get(tool_name)
            if not tool_function:
                raise ValueError(f"Tool '{tool_name}' not found.")
            
            # Await the tool if it's async
            if asyncio.iscoroutinefunction(tool_function):
                tool_result = await tool_function(**tool_args)
            else:
                tool_result = tool_function(**tool_args)

            # Add the tool result to the conversation history
            # The result needs to be a JSON string.
            tool_result_str = json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result)
            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": tool_result_str,
            })

        # --- Step 3: Call the model again with the tool result to get a final response ---
        logging.info("Sending tool results back to LLM for final response.")
        final_stream = await client.chat.completions.create(
            model=model,
            stream=True,
            messages=conversation_history,
        )
        async for chunk in final_stream:
            if chunk.choices[0].delta.content:
                yield f"0:{json.dumps(chunk.choices[0].delta.content)}\n"


@app.post("/chat")
async def handle_chat_data(request: Request, protocol: str = Query("data")):
    messages = request.messages
    openai_messages = convert_to_openai_messages(messages)
    
    response = StreamingResponse(stream_text(openai_messages, protocol))
    return response
