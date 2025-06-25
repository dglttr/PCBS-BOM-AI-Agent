import os
import json
import logging
from typing import List, Optional, cast
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .bom.router import router as bom_router
from .bom.logic import get_bom_data_with_alternatives, evaluate_alternative
from .llm import client
import asyncio

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(root_path="/api")
app.include_router(bom_router)

# In-memory cache for BOM data
bom_data_cache = {}

model = "gemini-2.5-flash-preview-05-20"
# model ="o4-mini-2025-04-16"

class Request(BaseModel):
    id: Optional[str] = None
    messages: List[ClientMessage]

available_tools = {
    "get_bom_data_with_alternatives": get_bom_data_with_alternatives,
    "evaluate_alternative": evaluate_alternative,
}

master_prompt = """
You are "B.O.M.B.A.", an expert manufacturing analyst. Your goal is to help the user process their Bill of Materials (BOM), find cost-saving alternatives, and present a comprehensive analysis.

**Your Reasoning Process:**

1.  **Acknowledge and Question:** When the user uploads a file, they will provide a `job_id`. Acknowledge the file and begin a friendly conversation to gather project requirements. Do NOT mention the `job_id`. You MUST ask for:
    *   The project's industry (e.g., Automotive, Consumer Electronics).
    *   The total order quantity for this production run.
    *   Any other critical performance requirements but only if necessary and cannot be inferred from the project's industry. Take the knowledge base into account.

2.  **Get the Data:** Once you have the assumptions, call the `get_bom_data_with_alternatives` tool, passing only the `job_id`.

3.  **Synthesize and Recommend:** A Python function will automatically evaluate all alternatives and provide you with a structured output of evaluation. You should return that output exactly without making any changes for every component in the BOM.
    
# Knowledge base
Use this knowledge base to help you make your decision:
## Special Industry Requirements for the Automotive Industry:
- RoHS compliant
- Should be lead free
- Should be able to handle temperatures between -55 °C to +85 °C    
"""

async def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    """
    Main agent logic.
    1.  Calls the LLM to understand user intent and get initial tool calls.
    2.  If `get_bom_data_with_alternatives` is called, it triggers a Python-based
        orchestration loop to evaluate all alternatives concurrently.
    3.  Sends all evaluation results back to the LLM for final synthesis.
    """
    conversation_history: List[ChatCompletionMessageParam] = [{"role": "system", "content": master_prompt}]
    conversation_history.extend(messages)

    logging.info("Agent loop started. Waiting for LLM to decide on initial tool call...")
    response = await client.chat.completions.create(
        messages=conversation_history,
        model=model,
        stream=False, # We need the full message to check for tool calls
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_bom_data_with_alternatives",
                    "description": "Parses a BOM file and enriches it with supplier data and potential alternatives. This is the first step and MUST be called before any analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "The unique ID of the BOM file processing job, which is available in the user's message.",
                            },
                             "assumptions": {
                                "type": "object",
                                "description": "User-provided project assumptions (e.g., industry, quantity).",
                            },
                        },
                        "required": ["job_id", "assumptions"],
                    },
                },
            },
            # The evaluate_alternative tool is now called by the backend, so it's not listed here for the LLM.
        ],
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

    # We are assuming the main flow is to call get_bom_data_with_alternatives
    # and then the python orchestrator takes over.
    if tool_calls[0].function.name == "get_bom_data_with_alternatives":
        logging.info("LLM requested 'get_bom_data_with_alternatives'. Starting Python orchestrator.")
        
        try:
            # --- Python Orchestrator Logic ---
            tool_args = json.loads(tool_calls[0].function.arguments)
            job_id = tool_args.get("job_id")
            assumptions = tool_args.get("assumptions", {})

            # 1. Get the summary of parts to evaluate
            summary = await get_bom_data_with_alternatives(job_id=job_id, cache=bom_data_cache)

            # 2. Create evaluation tasks for all alternatives
            evaluation_tasks = []
            for part in summary:
                evaluation_tasks.append(
                    evaluate_alternative(
                        part=part,
                        assumptions=assumptions,
                    )
                )
                        
            # 3. Run all evaluations concurrently
            logging.info(f"Starting concurrent evaluation of {len(evaluation_tasks)} alternatives...")
            evaluation_results = await asyncio.gather(*evaluation_tasks)
            
            logging.info("All evaluations complete.")

            # 4. Add all evaluation results as a single tool message to the conversation history
            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_calls[0].id,
                "content": json.dumps([
                    str(res) for res in evaluation_results
                ])
            })
            
            # 5. Final synthesis call to the LLM
            logging.info("Sending all evaluation results to LLM for final synthesis.")
            final_stream = await client.chat.completions.create(
                model=model,
                stream=True,
                messages=conversation_history,
            )
            async for chunk in final_stream:
                if chunk.choices[0].delta.content:
                    yield f"0:{json.dumps(chunk.choices[0].delta.content)}\n"
        except Exception as e:
            logger.error(f"Error during agent orchestration: {e}", exc_info=True)
            yield f"0:{json.dumps({'error': str(e)})}\n"

    else:
        # Fallback for any other tool calls (though none are defined for the LLM right now)
        logging.warning(f"Unhandled tool call: {tool_calls[0].function.name}")
        yield f"0:{json.dumps('An unexpected tool was called by the agent.')}\n"

@app.post("/chat")
async def handle_chat_data(request: Request, protocol: str = Query("data")):
    messages = request.messages
    openai_messages = convert_to_openai_messages(messages)

    # We need to manually "unwrap" the user message if it was a BOM request
    # so the LLM doesn't see the JSON structure.
    if openai_messages and openai_messages[-1]["role"] == "user":
        try:
            content_data = json.loads(str(openai_messages[-1]["content"]))
            if "bom_job_ids" in content_data:
                # This is a BOM request, format it for the agent
                job_ids_str = ", ".join(content_data["bom_job_ids"])
                text = content_data.get("text", "Processing files")
                openai_messages[-1]["content"] = f"{text}\n\n[Internal note: The job IDs for these files are: {job_ids_str}]"
            elif "bom_job_id" in content_data:
                 openai_messages[-1]["content"] = f"{content_data.get('text', 'Processing file')}\n\n[Internal note: The job ID for this file is: {content_data['bom_job_id']}]"
        except (json.JSONDecodeError, TypeError):
            pass # Not a BOM request, proceed normally

    response = StreamingResponse(stream_text(openai_messages, protocol))
    response.headers["x-vercel-ai-data-stream"] = "v1"
    return response
