# MD Reader / Dev Toolbox

MD Reader is a full-stack developer toolbox built with React, Vite, FastAPI, WebSockets, SSE streaming, S3-compatible storage, and an optional LLM-powered chat assistant. It includes live Markdown rendering, JSON utilities, Base64 conversion, Parquet inspection, document-aware chat, and code execution helpers.

## Features

- Live Markdown editor and preview over WebSocket.
- Floating AI chat panel that can use the active tool content as context.
- JSON formatter with validation, minify, text view, tree view, table view, search, and copy.
- Parquet reader that uploads `.parquet` files and returns schema plus a preview of up to 200 rows.
- Base64 encoder and decoder.
- JSON <-> YAML converter.
- Chat session persistence with local files and optional S3-compatible storage.
- Streaming chat responses using Server-Sent Events.
- Python and shell code execution endpoints with package detection, auto-install support, auto-fix attempts, and session-scoped output files.
- Docker Compose stack with frontend, backend, LocalStack S3, and Ollama.
- Helm chart for Kubernetes deployment.

## Tech Stack

- Frontend: React 18, TypeScript, Vite, React Router, Nginx for production serving.
- Backend: FastAPI, Uvicorn, WebSockets, SSE, markdown2, PyArrow, boto3.
- LLM: OpenAI-compatible API client. Works with OpenAI, Azure OpenAI, or Ollama through an OpenAI-compatible endpoint.
- Storage: Local disk plus optional S3-compatible storage. LocalStack is used in Docker for local S3.
- Deployment: Docker Compose, Dockerfiles, Jenkins pipelines, Helm chart.

## Project Structure

```text
.
|-- backend/
|   |-- main.py                 # FastAPI app, health check, routers, WebSocket route
|   |-- ws_handler.py           # Markdown WebSocket handler
|   |-- md_converter.py         # Markdown to HTML converter
|   |-- parquet_handler.py      # Parquet upload/read API
|   |-- s3_client.py            # S3/LocalStack wrapper
|   |-- chatbot/                # Chat, sessions, LLM client, tools, prompts
|   |-- Dockerfile
|   `-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- pages/              # Tool pages
|   |   |-- components/         # Editor, preview, chatbot, cards
|   |   |-- hooks/              # WebSocket, SSE chat, tool context hooks
|   |   `-- tools/registry.ts   # Tool route registry
|   |-- Dockerfile
|   |-- nginx.conf
|   `-- package.json
|-- helm/md-reader/             # Kubernetes Helm chart
|-- docker-compose.yml          # Local container stack
|-- Jenkinsfile*                # CI/CD pipelines
`-- main.py                     # Local launcher for backend and frontend
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm
- Docker and Docker Compose, if using the containerized setup
- Optional: Ollama, LocalStack, Helm, kubectl

## Environment Variables

For manual backend development, create `backend/.env`:

```env
OPENAI_API_KEY=your-api-key-or-ollama
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=

MAX_TOKENS=4096
CODE_MAX_TOKENS=16384
SESSION_TTL_MINUTES=60

AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
S3_ENDPOINT_URL=
S3_BUCKET=md-reader-sessions
```

For Ollama running locally, use an OpenAI-compatible base URL:

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=gemma4:31b-cloud
```

For LocalStack running locally:

```env
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
S3_ENDPOINT_URL=http://localhost:4566
S3_BUCKET=md-reader-sessions
```

## Quick Start With Docker Compose

From the repository root:

```powershell
docker compose up --build
```

Then open:

- Frontend: `http://localhost`
- LocalStack: `http://localhost:4566`
- Ollama: `http://localhost:11434`

The Docker stack includes:

- `frontend`: React app served by Nginx on port `80`.
- `backend`: FastAPI app on internal port `8000`.
- `localstack`: S3 emulator on port `4566`.
- `ollama`: local LLM server on port `11434`.
- `ollama-init`: one-off model pull job for `gemma4:31b-cloud`.

Note: the Compose backend service is internal only. The frontend Nginx container proxies `/api`, `/chat`, and `/ws` to the backend. To call `GET /health` directly in Docker mode, expose backend port `8000` in `docker-compose.yml`.

## Local Development

Install backend dependencies:

```powershell
python -m venv backend/venv
.\backend\venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

Install frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

Create `backend/.env`, then start both servers with the root launcher:

```powershell
python main.py
```

The launcher starts:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

The Vite dev server proxies `/api`, `/chat`, and `/ws` to the backend.

### Manual Server Commands

Backend only:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend only:

```powershell
cd frontend
npm run dev
```

## Frontend Routes

- `/` - Tool dashboard
- `/markdown` - Live Markdown reader
- `/json-formatter` - JSON formatter and explorer
- `/parquet-reader` - Parquet schema and preview reader
- `/base64` - Base64 converter
- `/json-yaml` - JSON/YAML converter

## Backend API

Main endpoints:

- `GET /health` - Backend health check.
- `WS /ws` - Markdown text in, rendered HTML out.
- `POST /api/parquet/read` - Upload and inspect a `.parquet` file.

Chat endpoints:

- `POST /chat/stream` - Streaming chat response using SSE.
- `POST /chat` - Non-streaming chat fallback.
- `GET /chat/history/{session_id}` - Restore chat history.
- `POST /chat/disconnect` - Save active session state.

Execution and generated files:

- `POST /chat/execute` - Execute Python or shell code and return the full result.
- `POST /chat/execute-stream` - Execute code with streaming output.
- `POST /chat/install` - Install Python packages.
- `POST /chat/auto-fix` - Ask the LLM to fix failed code and retry.
- `GET /chat/files/{session_id}` - List generated files for a session.
- `GET /chat/files/{session_id}/{filename}` - Download a generated file.
- `GET /chat/files/{session_id}/{filename}/url` - Return backend proxy download URL.

## Build Commands

Frontend production build:

```powershell
cd frontend
npm run build
```

Frontend preview:

```powershell
cd frontend
npm run preview
```

Backend dependency install:

```powershell
pip install -r backend/requirements.txt
```

## Helm Deployment

The chart lives at `helm/md-reader`.

Render templates locally:

```powershell
helm template md-reader .\helm\md-reader
```

Install or upgrade:

```powershell
helm upgrade --install md-reader .\helm\md-reader
```

Important chart values are in `helm/md-reader/values.yaml`:

- `backend.image.*`
- `frontend.image.*`
- `backend.env.openaiModel`
- `backend.secrets.*`
- `ollama.model`
- `localstack.persistence.*`
- `ollama.persistence.*`
- `ingress.*`

Before deploying, replace placeholder image registries such as `YOUR_PUBLIC_IP:9001` with your actual registry.

## Data and Persistence

- Chat memory is stored under `backend/memory` when running locally or through the backend volume in Docker.
- Generated execution output is stored under `backend/output`.
- In Docker and Helm, LocalStack provides S3-compatible storage for session files.
- The backend proxies file downloads through `/chat/files/...`, so browser clients do not need direct access to LocalStack or S3.

## Notes

- The backend requires `OPENAI_API_KEY` to be present, even when using Ollama.
- `OPENAI_BASE_URL` can point to OpenAI-compatible providers, including Ollama and Azure OpenAI.
- `S3_ENDPOINT_URL` should be empty for real AWS S3 and set to the LocalStack endpoint for local S3 emulation.
- The code execution features run subprocesses and can install packages. Use them only in trusted development or properly isolated deployment environments.
