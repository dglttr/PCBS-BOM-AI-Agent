import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
import logging

load_dotenv()

# Custom client class to handle content encoding issues
class CustomAsyncOpenAI(AsyncOpenAI):
    async def _process_response(self, *args, **kwargs):
        response = await super()._process_response(*args, **kwargs)
        # Remove content-encoding header to prevent issues with compressed data
        if hasattr(response, 'headers') and 'content-encoding' in response.headers:
            logging.info("Removing content-encoding header from response")
            del response.headers['content-encoding']
        return response

client = CustomAsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
) 