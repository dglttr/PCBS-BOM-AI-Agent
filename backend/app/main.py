import os
import json
import logging
from typing import List, Optional
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .bom.router import router as bom_router
from .bom.service import process_bom_data

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
    "get_bom_data_with_alternatives": process_bom_data,
}

master_prompt = """
You are "B.O.M.B.A.", an expert manufacturing analyst. Your goal is to help the user process their Bill of Materials (BOM), find cost-saving alternatives, and present a comprehensive analysis.

**Your Reasoning Process:**

1.  **Acknowledge and Question:** When the user uploads a file, they will provide a `job_id`. Acknowledge the file and begin a friendly conversation to gather project requirements. Do NOT mention the `job_id`. You MUST ask for:
    *   The project's industry (e.g., Automotive, Consumer Electronics).
    *   The total order quantity.
    *   Any other critical performance requirements.

2.  **Get the Data:** Once you have the assumptions, call the `get_bom_data_with_alternatives` tool, passing only the `job_id`.

3.  **Synthesize and Recommend:** The tool will return a list of parsed parts, including potential alternatives. Now, perform a holistic analysis of all this data in a single reasoning step. Your final response should be a well-structured markdown report that includes:
    *   A brief, friendly summary of the process.
    *   For each part in the BOM:
        *   Clearly state the original part's details.
        *   Evaluate its alternatives based on the user's assumptions. Make intelligent trade-offs between specs, price, and availability.
        *   State your final recommendation (either the original part or the best alternative).
        *   Provide clear, concise reasoning for your choice.
    *   Conclude with an overall summary of potential cost savings.
"""

async def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    conversation_history: List[ChatCompletionMessageParam] = [{"role": "system", "content": master_prompt}]
    conversation_history.extend(messages)

    logging.info("Agent loop started. Waiting for LLM response...")
    stream = await client.chat.completions.create(
        messages=conversation_history,
        model=model,
        stream=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_bom_data_with_alternatives",
                    "description": "Parses a BOM file and enriches it with supplier data and potential alternatives.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "The unique ID of the BOM file processing job.",
                            },
                        },
                        "required": ["job_id"],
                    },
                },
            }
        ],
    )

    tool_calls = []
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield f"0:{json.dumps(delta.content)}\n"
        if delta.tool_calls:
            if not tool_calls:
                for tc in delta.tool_calls:
                    if tc.function:
                        tool_calls.append({"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments or ""}})
            else:
                for i, tc in enumerate(delta.tool_calls):
                    if tc.function and tc.function.arguments:
                        tool_calls[i]["function"]["arguments"] += tc.function.arguments

    if tool_calls:
        logging.info(f"LLM decided to call {len(tool_calls)} tool(s).")
        conversation_history.append({"role": "assistant", "tool_calls": tool_calls})

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            # Ensure only the arguments defined in the tool's schema are passed
            if tool_name == "get_bom_data_with_alternatives":
                tool_args = {"job_id": tool_args.get("job_id")}

            tool_function = available_tools.get(tool_name)
            if not tool_function:
                raise ValueError(f"Tool '{tool_name}' not found.")
            
            tool_result = await tool_function(**tool_args)
            
            # The tool result for BOM data can be very large. We'll summarize it for the next LLM call
            # to avoid exceeding token limits, while keeping the full data for the final response.
            if tool_name == "get_bom_data_with_alternatives":
                summary = f"Successfully processed {len(tool_result)} parts. The data is now available for analysis."
                tool_content = summary
            else:
                tool_content = json.dumps(tool_result)

            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": tool_content,
            })

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
    return StreamingResponse(stream_text(openai_messages, protocol))
