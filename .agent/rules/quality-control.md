---
trigger: always_on
---

# Project Rules: Quality (Errors, Security, Git)

---

## Error Handling

### Custom Exceptions

```python
# src/core/exceptions.py

class ResearchAgentError(Exception):
    """Base exception for Research Agent."""
    pass

class SourceExtractionError(ResearchAgentError):
    """Failed to extract content from a source."""
    pass

class BiasClassificationError(ResearchAgentError):
    """Failed to classify source bias."""
    pass

class CrewExecutionError(ResearchAgentError):
    """CrewAI crew failed to complete."""
    pass
```

### Error Handling Pattern

```python
from src.core.exceptions import SourceExtractionError
import logging

logger = logging.getLogger(__name__)

def extract_article(url: str) -> ArticleContent:
    """Extract article content with fallback."""
    try:
        # Try primary extractor
        return _extract_trafilatura(url)
    except Exception as e:
        logger.warning(f"Trafilatura failed for {url}: {e}")
        
    try:
        # Fallback extractor
        return _extract_newspaper(url)
    except Exception as e:
        logger.error(f"All extractors failed for {url}: {e}")
        raise SourceExtractionError(f"Could not extract: {url}")
```

---

## Security Rules

1. **No API keys in code** - Use environment variables via `.env`
2. **No secrets in git** - Ensure `.env` is in `.gitignore`
3. **Validate all inputs** - Use Pydantic for API requests
4. **Rate limit web requests** - Implement polite delays
5. **Sanitize database inputs** - SQLAlchemy handles this

---

## Git Conventions

### Branch Naming

- `main` - Production-ready code
- `develop` - Integration branch
- `feature/description` - New features
- `fix/description` - Bug fixes
- `chore/description` - Maintenance

### Commit Messages

Use conventional commits:

```
feat: add bias classification tool
fix: handle empty RSS feed responses
docs: update README with CLI examples
chore: update dependencies
refactor: simplify crew orchestration
test: add unit tests for article extractor
```

---

## Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
        
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic]
```

---

## Testing

- **Framework:** pytest
- **Async:** pytest-asyncio
- **Coverage:** pytest-cov
- **Test naming:** `test_<function_name>_<scenario>`
- **Test location:** `tests/test_<module>/`
