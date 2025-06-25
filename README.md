# PCBS-BOM-AI-Agent

This repository contains an advanced, conversational AI agent designed to assist with the procurement and analysis of electronic components for manufacturing. The agent, named **B.O.M.B.A.** (BOM Processing and Management Bot Assistant), intelligently processes Bill of Materials (BOM) files, finds cost-saving alternatives, and presents its findings in a clear, human-readable report.

This project was built to tackle the "PCBA BOM Processing" hackathon challenge, demonstrating a modern, tool-calling AI architecture.

## Key Features

- **Conversational Interface:** Instead of static forms, the user interacts with the agent through a natural, back-and-forth conversation to define project requirements.
- **Dynamic Requirement Gathering:** The agent intelligently asks clarifying questions based on the content of the uploaded BOM to understand the specific needs of the project.
- **Multi-File Upload:** Supports uploading and processing up to 10 BOM files at once via drag-and-drop or a file selector.
- **AI-Powered Validation:** Uses a powerful LLM (Google's Gemini 2.5 Pro) to evaluate potential alternative parts against the project's requirements, making nuanced, context-aware decisions.
- **Automated Data Enrichment:** Fetches detailed component data, including specifications, pricing, and potential alternatives, from the Octopart API.
- **Cost & Lead Time Analysis:** Provides a clear summary of potential cost savings and lead time improvements when valid alternatives are found.
- **Robust Caching:** Implements a file-based cache for API calls to improve performance and manage rate limits.

## The "Analyst-in-the-Loop" Architecture

After several iterations, we settled on a sophisticated, tool-calling agent architecture that we call the "Analyst-in-the-Loop". This design provides the best balance of reliability, performance, and intelligent, nuanced reasoning.

The agent's workflow is as follows:

1.  **Conversational Setup:** When a user uploads a BOM, the agent initiates a conversation to gather critical project assumptions (industry, order quantity, etc.).
2.  **Tool Call 1: `get_bom_data_with_alternatives`:** Once the agent has the necessary assumptions, it calls its first tool. This tool is a Python function that:
    *   Parses the raw BOM file (CSV, XLS, XLSX).
    *   Uses an LLM to identify the correct column mapping (e.g., 'MPN', 'Quantity').
    *   Uses another LLM call for each row to parse it into a structured object.
    *   Calls the Octopart API to fetch detailed data for the original part and a list of potential `similarParts`.
    *   Returns a large, structured list of all this raw data back to the agent.
3.  **Tool Call 2 (in a loop): `evaluate_alternative`:** With the raw data now in its context, the agent begins its core reasoning loop. For each part that has alternatives, it calls the `evaluate_alternative` tool.
    *   This tool takes the original part, one alternative, and the project assumptions, and sends them to the LLM with a specific prompt asking: "Is this a valid substitute?"
    *   The LLM returns a structured response: `{"is_valid": boolean, "reasoning": "..."}`.
4.  **Final Synthesis:** After evaluating all alternatives for all parts, the agent has a complete picture. It then uses one final, comprehensive LLM call to generate a user-facing markdown report, summarizing its findings, explaining its reasoning for each recommendation, and calculating the total potential cost savings.

This "Team of Specialists" approach, where the main agent orchestrates calls to smaller, focused tools, proved to be more reliable and debuggable than a single "Master Craftsman" prompt, especially when dealing with the complexities of external API data and structured outputs.

## Project Structure

- `frontend/`: The Next.js 15 frontend.
  - `src/components/chat.tsx`: The main chat interface component, orchestrating the frontend logic.
  - `src/components/bom-display.tsx`: The component for rendering the final results table.
- `backend/`: The FastAPI (Python 3.12+) backend.
  - `app/main.py`: The main FastAPI application, containing the master agent prompt and the primary `/api/chat` endpoint.
  - `app/bom/logic.py`: Contains all the core functions that are exposed to the agent as "tools" (`get_bom_data_with_alternatives`, `evaluate_alternative`).
  - `app/bom/octopart_client.py`: The client for interacting with the Nexar/Octopart API.
  - `app/bom/schemas.py`: Defines all Pydantic models for structured data validation.
- `Makefile`: Provides convenient commands for managing the development environment.
- `docker-compose.yml`: Defines the services for local development and deployment.

## Prerequisites & Setup

### Environment Variables

Before running, create a `backend/.env` file with the following content:

```
# Get your free key from https://developers.generativeai.google.com/
GEMINI_API_KEY="your_gemini_api_key_here"

# Get your free key from https://octopart.com/api/register
NEXAR_API_KEY="your_nexar_api_key_here"
```

### Installation and Running

This project is managed with `make`.

1.  **Install all dependencies:**
    ```bash
    make install
    ```
2.  **Run the development servers:**
    ```bash
    make backend-run
    ```
    In a separate terminal:
    ```bash
    make frontend-run
    ```

The application will be available at `http://localhost:3000`.

## Available Makefile Commands

- `make install`: Installs all dependencies.
- `make backend-run`: Starts the FastAPI backend server.
- `make frontend-run`: Starts the Next.js frontend server.
- `make up`: Runs all services with Docker Compose.
- `make down`: Stops all Docker services.
- `make logs`: Tails logs from Docker services.
- `make sh-backend`: Opens a shell into the running backend container.
- `make sh-frontend`: Opens a shell into the running frontend container.
