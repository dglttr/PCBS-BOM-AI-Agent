import json
import logging
import asyncio
from typing import Dict, Any, List, cast, AsyncGenerator
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from ..llm import client
from ..utils.tools import get_weekday_names
from .schemas import ProductionPlanResponse, ProductionPlanChunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global storage for production plans
production_plans_cache: Dict[str, Any] = {}

async def optimize_production_plan(
    job_id: str,
    current_stock: int = 0,
    scrap_rate: float = 0.05,
    cache: Dict[str, Any] = {},
) -> AsyncGenerator[ProductionPlanChunk, None]:
    """
    Process a production plan using the LLM and return an optimized schedule.
    
    Args:
        job_id: The unique ID of the uploaded production plan
        current_stock: The current stock level of the product
        scrap_rate: The scrap rate to account for in production
        cache: Optional cache dictionary to store results
    
    Yields:
        ProductionPlanChunk objects with parts of the optimized plan as they become available
    """
    # First, yield a special marker to indicate the tool has started
    yield ProductionPlanChunk(text="__TOOL_START:optimize_production_plan__")
    
    # Use the provided cache or fall back to the global cache
    cache_to_use = cache if cache is not None else production_plans_cache
    
    # Check if the job_id exists in the cache
    if job_id not in cache_to_use:
        logger.error(f"Production plan with job_id {job_id} not found")
        raise ValueError(f"Production plan with job_id {job_id} not found")
    
    # Get the production plan data
    data = cache_to_use[job_id]
    
    # Convert the data to JSON for the LLM
    data_json = json.dumps(data)
    
    # Create the system instruction
    system_instruction = """
# Role
You are an expert in the field of manufacturing and supply chain management.
You analyze the production and sales orders of a company, aiming to optimize their scheduling.
Sales orders are fixed, but you can change both the quantity and the date of production orders.
Be very critical with the existing production plan. Chances are you need to change the production orders quite significantly.
Sales orders are negative, production orders are positive.
You are concise and to the point.

# Background information
- The maximum capacity of the factory is 100 units of product A per day. The capacity must NOT be exceeded at any time! You must always respect the daily capacity limit. If the capacity is exceeded, you must split the production order over multiple days.
- When computing the quantity needed, first subtract the current stock before calculating the scrap rate.
- Note that the production order needs to happen at least one day before the sales order. If the quantity on that day exceeds the capacity, production needs to start even earlier.
- Take the scrap rate into account. This means that you need to produce more than the sales order quantity to account for the scrap.
- Of the products produced, only that are scrapped cannot be used anymore. They are discarded. They do NOT enter the inventory.
- No production is allowed on weekends (Saturday and Sunday). You should use the get_weekday_names tool to check the weekday of dates.

# Objective
You optimize the production plan to optimize the following KPIs:
- OTIF (On Time In Full): Aim to never miss a sales order due date. This is the most important KPI. Stockouts should be avoided if at all possible.
- At the same time, aim to minimize the number of days between production and sales to reduce finished goods inventory (try to aim for Just-In-Time production).

# Output
You first output should always be a table in valid Markdown format. The table includes the rescheduled, optimized production orders as well as the sales orders (which you must not change).
The following columns are required:
- Date
- Product
- Type (🛠️ Production Order or 💰 Sales Order)
- Quantity (negative, if a sales order, positive if a production order)

Below that, break down the calculations and very briefly explain assumptions and reasoning.
"""
    
    # Create the user prompt
    user_prompt = f"""
Please analyze the following data and output an optimized production plan:
{data_json}

The current stock level is {current_stock} units of Product A.
The scrap rate is {scrap_rate*100:.2f}%.
"""
    
    try:
        logging.info(f"Calling LLM inside optimize_production_plan with user prompt: {user_prompt}")        
        # Initialize conversation history
        conversation_history: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ]

        # Call the LLM to process the production plan
        response = await client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=conversation_history,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weekday_names",
                        "description": "Gets the weekday name for each date.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "dates": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    },
                                    "description": "List of dates to check in YYYY-MM-DD format."
                                }
                            },
                            "required": ["dates"]
                        }
                    }
                }
            ],
            stream=False,    # need full response to check for tool calls
            tool_choice="required",
            #reasoning_effort="low"
        )
        
        # Process the initial response
        message = response.choices[0].message
        tool_calls = message.tool_calls
        logging.info(f"Tool calls inside optimize_production_plan: {tool_calls}")
        
        # If there are tool calls, handle them
        if tool_calls:
            # Add the assistant's response with tool calls to the conversation history
            conversation_history.append({
                "role": "assistant",
                "tool_calls": cast(list, tool_calls)
            })
            
            # Process each tool call
            for tool_call in tool_calls:
                if tool_call.function.name == "get_weekday_names":
                    # Parse the arguments
                    args = json.loads(tool_call.function.arguments)
                    dates = args.get("dates", [])
                    
                    # Execute the tool
                    result = get_weekday_names(dates)
                    
                    # Add the tool result to the conversation history
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
                else:
                    logging.info(f"Unknown tool call in optimize_production_plan: {tool_call.function.name}")
            
        else:
            logging.info(f"No tool call inside optimize_production_plan")
            yield ProductionPlanChunk(text=message.content or "")
            return
        
        # Make a final call to get the complete response
        logging.info(f"Final synthesis LLM call inside optimize_production_plan with conversation history: {conversation_history}")

        # Get the final response with streaming enabled
        final_response_stream = await client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=conversation_history,
            stream=True,
            #reasoning_effort="low"
        )
        
        # Stream the chunks directly
        async for chunk in final_response_stream:
            if chunk.choices[0].delta.content:
                yield ProductionPlanChunk(text=chunk.choices[0].delta.content)
        
        logging.info(f"Final synthesis completed successfully")
    
    except Exception as e:
        logger.error(f"Error when optimizing production plan: {e}", exc_info=True)
        yield ProductionPlanChunk(text=f"Error when optimizing production plan: {str(e)}") 