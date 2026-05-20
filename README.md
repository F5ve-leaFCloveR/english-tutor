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
