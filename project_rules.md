# Research Agent - Project Rules & Conventions

**Project:** Research Agent  
**Created:** January 16, 2026  

---

> [!NOTE]
> Project rules have been split into separate files for better organization. Each file is under 12,000 characters.

## Rule Files

| File | Contents |
|------|----------|
| [rules_overview.md](rules_overview.md) | Tech stack, dependencies, project structure |
| [rules_python.md](rules_python.md) | Python coding conventions, naming, type hints, docstrings |
| [rules_crewai.md](rules_crewai.md) | CrewAI agent, tool, and crew patterns |
| [rules_backend.md](rules_backend.md) | Database (SQLAlchemy), API (FastAPI), CLI (Click) |
| [rules_frontend.md](rules_frontend.md) | Next.js conventions, components, API client |
| [rules_quality.md](rules_quality.md) | Error handling, security, git conventions, testing |

---

## Quick Reference: Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Agent Framework | CrewAI |
| Primary LLM | OpenRouter (free tier) |
| Database | SQLite + SQLAlchemy |
| Backend API | FastAPI |
| Frontend | Next.js 15 + shadcn/ui |
| CLI | Click + Rich |

---

## Quick Reference: Key Patterns

### Python Style
- Ruff for formatting/linting
- mypy strict mode
- Google-style docstrings
- Type hints everywhere

### Commits
```
feat: add feature
fix: bug fix
docs: documentation
chore: maintenance
refactor: code cleanup
test: add tests
```

### Branch Naming
- `main` - production
- `feature/description` - new features
- `fix/description` - bug fixes
