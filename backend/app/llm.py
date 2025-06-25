import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

client = AsyncOpenAI(
    api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
) 