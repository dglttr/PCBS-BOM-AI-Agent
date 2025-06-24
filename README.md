# AI SDK Python Streaming POC

This repository contains a proof-of-concept monorepo demonstrating how to stream chat completions from a Python (FastAPI) backend to a Next.js frontend using the Vercel AI SDK.

## Features

- **Streaming API:** The backend streams chat completions using the AI SDK's data stream protocol.
- **Function Calling:** The chatbot can call functions, for example, to get the current weather.
- **Modern UI:** The frontend is built with Next.js, shadcn/ui, and Tailwind CSS.

## Project Structure

- `frontend/`: Contains the Next.js 15 frontend application.
  - `src/app/(chat)`: The main chat interface.
  - `src/components`: Contains the React components, including the chat UI.
  - `src/lib`: Contains utility functions and the AI SDK setup.
- `backend/`: Contains the FastAPI (Python 3.12+) backend application.
  - `app/main.py`: The main FastAPI application, with the `/api/chat` endpoint.
  - `app/utils`: Contains utility functions for the backend, including prompt engineering and tool definitions.
- `Makefile`: Provides convenient commands for managing the local development environment.
- `docker-compose.yml`: Defines the services for both local development and cloud deployment.

## Networking and Reverse Proxy

The application uses [Traefik](httpss://traefik.io/traefik/) as a reverse proxy to manage incoming traffic and route it to the appropriate service. This is configured in the `docker-compose.yml` file.

### Key Configuration Details

- **Entry Point**: The reverse proxy is configured to listen for HTTP traffic on port `8080`. Port 80 is often reserved or blocked on cloud platforms, so 8080 was chosen to ensure reliable access.
- **Service Routing**:
  - The **frontend** service is served by default for any requests to the root path (`/`).
  - The **backend** service is served for any requests to the `/api` path.
- **Authentication**: The entire application is protected by basic authentication (username/password), which is configured in Traefik.

This setup allows both the frontend and backend to be served from the same domain and port, simplifying the deployment and access.

## Prerequisites

### For Local Development

- [Docker](https://www.docker.com/get-started)
- [pnpm](https://pnpm.io/installation)
- [uv](https://github.com/astral-sh/uv) (Python package manager)

## Backend Configuration

The backend can be configured to use either OpenAI or Azure OpenAI as the provider for chat completions.

### Azure OpenAI Provider (Default)

**Required Environment Variables:**

- `AZURE_OPENAI_ENDPOINT`: The endpoint URL for your Azure OpenAI resource.
- `AZURE_OPENAI_API_KEY`: Your secret API key for the Azure OpenAI service.
- `AZURE_OPENAI_DEPLOYMENT`: The name of your model deployment in Azure AI Studio.

### OpenAI Provider

**Required Environment Variables:**

- `OPENAI_API_KEY`: Your secret API key for OpenAI.
- `OPENAI_MODEL` (optional): The model to use for chat completions (e.g., `gpt-4o`). Defaults to `gpt-4o`.

## Local Development Setup

Follow these steps to set up and run the development environment locally.

### 1. Environment Variables

Create a `.env` file in the root of the project by copying the example file:

```bash
cp .env.example .env
```

Then, add the required environment variables to the `.env` file based on your chosen provider. See the [Backend Configuration](#backend-configuration) section for details.

### 2. Installation

Install all frontend and backend dependencies using the main `install` command. This will create a virtual environment for the backend in `backend/.venv` and install all necessary packages.

```bash
make install
```

### 3. Running the Development Servers

You have two options for running the development environment:

**Option 1: Run services locally**

You can run the backend and frontend development servers in separate terminals.

**To run the backend (FastAPI):**

```bash
make backend-run
```

The server will be available at `http://127.0.0.1:8000`.

**To run the frontend (Next.js):**

```bash
make frontend-run
```

The server will be available at `http://localhost:3000`.

**Option 2: Run services with Docker**

You can also run both services concurrently using Docker.

```bash
make up
```

This will start both the backend and frontend services. The frontend will be available at `http://localhost:8080`.

## Available Makefile Commands

Here is a summary of the most useful commands defined in the `Makefile`.

### Local Development

- `make install`: Installs all dependencies for both frontend and backend.
- `make install-backend`: Creates a virtual environment and installs Python dependencies.
- `make install-frontend`: Installs Node.js dependencies.
- `make backend-run`: Starts the backend development server.
- `make frontend-run`: Starts the frontend development server.

### Docker

- `make up`: Start all services in detached mode using Docker Compose with Bake.
- `make down`: Stop and remove all Docker containers, networks, and volumes.
- `make logs`: Follow the logs for all running services.
- `make sh-backend`: Get a shell into the running backend Docker container.
- `make sh-frontend`: Get a shell into the running frontend Docker container.
