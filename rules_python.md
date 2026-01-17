# Project Rules: Python Conventions

---

## Python Style

- **Formatter:** Ruff (replaces Black + isort)
- **Linter:** Ruff
- **Type Checker:** mypy (strict mode)
- **Line Length:** 88 characters
- **Quotes:** Double quotes for strings

### Ruff Configuration

```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 88
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
]
ignore = [
    "E501",   # line too long (handled by formatter)
    "B008",   # function call in argument defaults
]

[tool.ruff.isort]
known-first-party = ["src"]
```

### Mypy Configuration

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["crewai.*", "ddgs.*", "trafilatura.*"]
ignore_missing_imports = true
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| **Files** | snake_case | `bias_classifier.py` |
| **Classes** | PascalCase | `BiasClassifierTool` |
| **Functions** | snake_case, verb prefix | `get_bias_rating()` |
| **Variables** | snake_case | `source_domain` |
| **Constants** | SCREAMING_SNAKE | `POLITICAL_SCALE` |
| **Private** | Leading underscore | `_parse_response()` |

---

## Type Hints

Always use type hints:

```python
# Good
def analyze_source(url: str, timeout: int = 30) -> SourceAnalysis:
    ...

# Bad
def analyze_source(url, timeout=30):
    ...
```

---

## Docstrings

Use Google-style docstrings:

```python
def classify_bias(source_domain: str, article_text: str) -> BiasResult:
    """Classify the political bias of a news source.
    
    Attempts to look up the source in the local MBFC dataset first.
    Falls back to LLM-based classification if not found.
    
    Args:
        source_domain: The domain of the news source (e.g., "cnn.com")
        article_text: The article content for LLM analysis
        
    Returns:
        BiasResult with political_leaning (-4 to +4) and confidence score
        
    Raises:
        ClassificationError: If both dataset and LLM methods fail
    """
    ...
```
