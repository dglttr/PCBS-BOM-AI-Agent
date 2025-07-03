import json
import logging
from typing import List, Optional, cast, Dict, Any
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .production.router import router as production_router
from .llm import client
import asyncio
from .production.logic import optimize_production_plan, production_plans_cache

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(root_path="/api")
app.include_router(production_router)

model = "gemini-2.5-flash"

class Request(BaseModel):
    id: Optional[str] = None
    messages: List[ClientMessage]

available_tools = {
    "optimize_production_plan": optimize_production_plan,
}

tools: List[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "optimize_production_plan",
            "description": "Optimizes the production plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID of the production plan to optimize."
                    },
                    "current_stock": {
                        "type": "number",
                        "description": "The current stock level of the product."
                    },
                    "scrap_rate": {
                        "type": "number",
                        "description": "The scrap rate to account for in production (default is 5%)."
                    }
                },
                "required": ["job_id", "current_stock", "scrap_rate"]
            }
        }
    },
]

system_prompt = """
You are a production planning assistant.
You analyze the production and sales orders of a company, aiming to optimize their scheduling. To do so, you will use the `optimize_production_plan` tool.

**Your Workflow:**

1.  **Acknowledge and Guide:** When a user starts a conversation, guide them to upload a production plan CSV file. After they upload the file (you will receive a `job_id`), acknowledge receipt and begin a friendly conversation to gather additional information. Do NOT mention the `job_id` to the user. You MUST ask for:
    *   The current stock level of the product
    *   The scrap rate to account for in production (e.g., 5%)
2.  **Start optimization:** Once you have the assumptions, call the `optimize_production_plan` tool, passing the `job_id`, `current_stock`, and `scrap_rate`. The `optimize_production_plan` tool will provide you with a structured output of an optimized production plan. You should return that output exactly without making any changes.
3.  **Explain and Answer Questions:** Be prepared to explain the optimization decisions and answer any questions the user might have about the production plan.
"""

async def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    """
    Main agent logic.
    1.  Calls the LLM to understand user intent and get initial tool calls.
    2.  If `optimize_production_plan` is called, it triggers a Python-based
        orchestration loop to optimize the production plan.
    3.  Directly returns the tool result as the final response.
    """
    conversation_history: List[ChatCompletionMessageParam] = [{"role": "system", "content": system_prompt}]
    conversation_history.extend(messages)

    logging.info(f"Agent loop started. Last message: {conversation_history[-1]}")
    response = await client.chat.completions.create(
        messages=conversation_history,
        model=model,
        stream=False, # We need the full message to check for tool calls
        tools=tools
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if not tool_calls:
        # No tool call, just stream back the text response
        yield f"0:{json.dumps(response_message.content)}\n"
        return

    # Add the assistant's response (which contains the tool call) to history
    conversation_history.append({
        "role": "assistant",
        "tool_calls": cast(list, response_message.tool_calls)
    })

    # We are assuming the main flow is to call optimize_production_plan
    # and then the python orchestrator takes over.
    if tool_calls[0].function.name in ["optimize_production_plan"]:
        # Handle tool calls for production planning
        try:
            tool_name = tool_calls[0].function.name
            tool_args = json.loads(tool_calls[0].function.arguments)
            
            # Execute the tool
            logging.info(f"Executing tool: {tool_name} with arguments: {tool_args}")
            
            # Add the cache parameter
            tool_args["cache"] = production_plans_cache
            
            # Stream the tool results directly to the client
            async for chunk in optimize_production_plan(**tool_args):
                logging.info(f"Streaming chunk: {chunk.text[:50].replace('\n', ' ')}...")
                yield f"0:{json.dumps(chunk.text)}\n"
            
            logging.info("Finished streaming production plan optimization results")
            
        except Exception as e:
            logger.error(f"Error processing tool call: {e}", exc_info=True)
            yield f"0:{json.dumps({'error': str(e)})}\n"
    else:
        # Fallback for any other tool calls (though none are defined for the LLM right now)
        logging.warning(f"Unhandled tool call: {tool_calls[0].function.name}")
        yield f"0:{json.dumps('An unexpected tool was called by the agent.')}\n"

@app.post("/chat")
async def handle_chat_data(request: Request, protocol: str = Query("data")):
    messages = request.messages
    openai_messages = convert_to_openai_messages(messages)

    # We need to manually "unwrap" the user message if it was a data request
    # so the LLM doesn't see the JSON structure.
    if openai_messages and openai_messages[-1]["role"] == "user":
        try:
            content_data = json.loads(str(openai_messages[-1]["content"]))
            if "production_plan_job_id" in content_data:
                 openai_messages[-1]["content"] = f"{content_data.get('text', 'Processing production plan')}\n\n[Internal note: The job ID for this production plan is: {content_data['production_plan_job_id']}]"
        except (json.JSONDecodeError, TypeError):
            pass # Not a data request, proceed normally

    response = StreamingResponse(stream_text(openai_messages, protocol))
    response.headers["x-vercel-ai-data-stream"] = "v1"
    return response
