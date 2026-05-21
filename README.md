# English Tutor — Stage 0 CLI

Voice-first CLI for practicing English via LLM roleplay.

## Setup
1. `cp .env.example .env` and fill in your OpenRouter API key.
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -e ".[dev]"`
4. `pytest` — all tests should pass.

## Run a session
`tutor interview` — starts a tech-interview behavioral practice session.

Press Enter to start/stop recording each turn. Type `end` instead of speaking to finish the session.

## Browser UI (Stage 2a)

After Stage 2a, the project has a localhost web UI alongside the CLI.

### Run the web UI

```bash
./scripts/build_and_serve.sh
# Then open http://127.0.0.1:8000 in your browser.
```

The build step:
1. Installs frontend deps with `npm install`
2. Builds the React app into `tutor/web/static/`
3. Starts FastAPI which serves both the API (`/api/*`) and the built frontend (`/` + `/static/*`)

### CLI still works

The CLI is untouched:
```bash
tutor interview
tutor review
tutor stats
tutor list-scenarios
```

### Dev workflow

For frontend iteration:
```bash
# terminal 1
uvicorn tutor.web.api:create_app --factory --reload --host 127.0.0.1 --port 8000

# terminal 2
cd frontend && npm run dev   # vite at localhost:5173 with proxy to :8000
```
