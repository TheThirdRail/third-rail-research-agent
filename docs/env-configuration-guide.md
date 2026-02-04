# Environment Configuration Guide

This document explains every section of your `.env` file and provides step-by-step instructions for acquiring necessary credentials.

---

## Section 1: Application Settings

```ini
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
```

| Variable | Purpose | Valid Values |
| :--- | :--- | :--- |
| `APP_ENV` | Environment mode. Affects logging and error handling. | `development`, `production`, `test` |
| `DEBUG` | Enable verbose debugging output. | `true`, `false` |
| `LOG_LEVEL` | Controls Python logging verbosity. | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**No action required.** Defaults are fine for local development.

---

## Section 2: API Settings

```ini
API_HOST=0.0.0.0
API_PORT=8000
```

| Variable | Purpose |
| :--- | :--- |
| `API_HOST` | IP address the FastAPI backend listens on. `0.0.0.0` means all interfaces. |
| `API_PORT` | Port for the backend. Default `8000`. |

**No action required** unless you have a port conflict.

---

## Section 3: Web UI Settings

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

| Variable | Purpose |
| :--- | :--- |
| `NEXT_PUBLIC_API_URL` | URL the Next.js frontend uses to call the backend. Must match `API_HOST:API_PORT`. |

**No action required** for standard local development. If running in Docker, this might change to `http://backend:8000`.

---

## Section 4: Database

```ini
DATABASE_URL=sqlite:///data/research_agent.db
```

| Variable | Purpose |
| :--- | :--- |
| `DATABASE_URL` | Connection string for your database. |

### Is this correct?

**Yes.** The path `sqlite:///data/research_agent.db` is a **relative path** from the project root. The application automatically creates the `data/` folder if it doesn't exist. No changes needed.

> [!TIP]
> For PostgreSQL in production, use: `postgresql://user:password@host:5432/dbname`

---

## Section 5: LLM Provider Selection

```ini
LLM_PROVIDER=openrouter
```

| Variable | Purpose |
| :--- | :--- |
| `LLM_PROVIDER` | The **default** LLM provider for agents. |

### Valid Options

`openrouter`, `openai`, `anthropic`, `gemini`, `groq`, `cerebras`, `sambanova`, `mistral`, `ollama`

> [!IMPORTANT]
> **Model Selection is done in the UI.** You do NOT need `SELECTED_MODEL` or `ANALYSIS_MODEL` in your `.env` file. Those are managed via the Settings page in the web dashboard.

---

## Section 6: API Keys

This is the only section that requires action. Fill in keys for providers you plan to use.

### OpenRouter (Recommended)

```ini
OPENROUTER_API_KEY=mock-or-v1-xxxxxxxx
```

**How to get:**

1. Go to [openrouter.ai](https://openrouter.ai/)
2. Sign in with Google/GitHub
3. Navigate to **Keys** (top right menu)
4. Create a new key, copy it

**Why recommended:** OpenRouter aggregates 100+ models from various providers (including free ones), so you only need one key to access OpenAI, Claude, Gemini, Llama, etc.

---

### OpenAI

```ini
OPENAI_API_KEY=mock-xxxxxxxx
```

**How to get:**

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign in
3. Click your profile → **API keys**
4. Create new secret key

---

### Anthropic (Claude)

```ini
ANTHROPIC_API_KEY=mock-ant-xxxxxxxx
```

**How to get:**

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign in
3. Navigate to **Settings → API Keys**
4. Create new key

---

### Google Gemini

```ini
GEMINI_API_KEY=your_gemini_api_key_here
```

**How to get:**

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy the key

---

### Groq

```ini
GROQ_API_KEY=your_groq_api_key_here
```

**How to get:**

1. Go to [console.groq.com](https://console.groq.com/)
2. Sign in
3. Navigate to **API Keys**
4. Create new key

**Note:** Groq offers **free tier** with very fast inference.

---

### Cerebras

```ini
CEREBRAS_API_KEY=cmock-xxxxxxxx
```

**How to get:**

1. Go to [cloud.cerebras.ai](https://cloud.cerebras.ai/)
2. Sign up / Sign in
3. Navigate to **API Keys**
4. Generate a key

**Note:** Cerebras offers **1 million free tokens/day**.

---

### SambaNova

```ini
SAMBANOVA_API_KEY=xxxxxxxx
```

**How to get:**

1. Go to [cloud.sambanova.ai](https://cloud.sambanova.ai/)
2. Sign up / Sign in
3. Navigate to API settings
4. Generate a key

---

### Mistral AI

```ini
MISTRAL_API_KEY=xxxxxxxx
```

**How to get:**

1. Go to [console.mistral.ai](https://console.mistral.ai/)
2. Sign in
3. Navigate to **API Keys**
4. Create new key

---

### xAI (Grok)

```ini
XAI_API_KEY=your_xai_api_key_here
```

**How to get:**

1. Go to [console.x.ai](https://console.x.ai/)
2. Sign in with your X (Twitter) account
3. Request API access (may require waitlist)
4. Generate a key

---

## Section 7: Local LLM (Ollama)

```ini
OLLAMA_BASE_URL=http://localhost:11434
```

| Variable | Purpose |
| :--- | :--- |
| `OLLAMA_BASE_URL` | URL to your local Ollama server. |

**How to set up Ollama:**

1. Download from [ollama.ai](https://ollama.ai/)
2. Install and run `ollama serve`
3. Pull a model: `ollama pull llama3`
4. Keep the default URL unless you changed ports

---

## Quick Start Checklist

- [ ] Copy `.env.example` to `.env`
- [ ] Choose your `LLM_PROVIDER` (recommend `openrouter` to start)
- [ ] Get API key for your chosen provider
- [ ] Paste API key into `.env`
- [ ] Run the backend: `uvicorn src.api.main:app --reload`
- [ ] Select specific models in the UI Settings page
