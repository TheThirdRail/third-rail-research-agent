# Docker Restart Instructions

Use this when you want to rebuild the local containers and try the app in the browser.

## 1. Open PowerShell at the repo root

```powershell
cd D:\Coding\Research-Agent
```

## 2. Confirm Docker is running

```powershell
docker version
docker compose version
```

If either command fails, start Docker Desktop and run the commands again.

## 3. Check your local `.env`

```powershell
Test-Path .env
```

If it prints `False`, create one from the example:

```powershell
Copy-Item .env.example .env
```

Before starting the app, edit `.env` and set at least one real LLM provider key, such as `OPENROUTER_API_KEY`. If you need admin UI operations, set a local `ADMIN_API_KEY` too:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep secrets local. Do not paste real keys into chat, notes, screenshots, or commits.

## 4. Stop the existing containers

```powershell
docker compose down
```

This stops the backend and frontend without deleting `./data/research_agent.db`.

## 5. Rebuild and start fresh containers

```powershell
docker compose build --no-cache
docker compose up -d
```

First rebuilds can take several minutes.

## 6. Initialize or migrate the database

```powershell
docker compose exec backend research-agent init
docker compose exec backend research-agent health --strict
```

`research-agent init` is the operator-controlled database initialization and migration step for this project.

## 7. Confirm the containers are healthy

```powershell
docker compose ps
curl http://localhost:8000/health
```

Expected services:

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

## 8. Open the app

Go to:

```text
http://localhost:3000
```

## Useful follow-up commands

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose restart backend
docker compose restart frontend
```

To include the optional Ollama container:

```powershell
docker compose --profile local-llm up -d
```

## Reset local data only if needed

This deletes your local SQLite database:

```powershell
docker compose down
Remove-Item .\data\research_agent.db
docker compose up -d
docker compose exec backend research-agent init
```
