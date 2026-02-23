# AGENTS.md

## AGENT OPERATING MANUAL: Python Script & Report Projects

---

This document provides standardized operating instructions for agentic coding agents (including LLM-based developers) working in this repository. Follow these rigorously to maximize code quality, reproducibility, maintainability, and cross-agent collaboration.

---

## 1. Build & Test Execution

#### 1.1 Running Scripts (HTML report generation)
- All scripts should be executable via:
  ```sh
  python <script_name.py>
  ```
- Avoid hardcoding file paths; accept input/output locations as CLI args or via config files when possible.
- Scripts should produce outputs in `/reports/`, `/reports/figures` or a designated output directory.

#### 1.2 Project Linting
- Lint all source files before PRs/commits:
  ```sh
  pip install flake8
  flake8 .
  ```
- Optionally use: `black .` (formatter), `isort .` (import sorting), or `ruff .`

#### 1.3 Running Tests
- Prefer [pytest](https://docs.pytest.org/):
  ```sh
  pytest
  # Single test function:
  pytest path/to/test_file.py::TestClassName::test_func_name
  ```
- Unittest discovery is also supported:
  ```sh
  python -m unittest discover
  ```
- Place all tests in `tests/` or co-locate with scripts as `test_*.py` files.

#### 1.4 Dependency Management
- Document dependencies in `requirements.txt` or `pyproject.toml`.
- Use virtualenv or conda for isolation; include instructions if custom.

---

## 2. CODE STYLE & DESIGN GUIDELINES

Follow [PEP 8](https://peps.python.org/pep-0008/), [PEP 257](https://peps.python.org/pep-0257/) (docstrings), and these agent-tailored conventions:

### 2.1 Imports & Module Structure
- Standard library imports first, then third-party, then local—separated by blank lines (use `isort` to autoformat).
- No unused imports; import only what is used.
- Relative imports only if unavoidable (prefer absolute).
- Scripts should be runnable both as main and importable modules (use `if __name__ == "__main__":` for CLI logic).

### 2.2 Formatting & Whitespace
- Use 4 spaces per indentation level (never tabs).
- Max line length: 79 characters for code, 72 for comments/docstrings.
- Surround top-level functions/classes with two blank lines, methods with one blank line.
- No trailing whitespace—configure editor/CI to strip automatically.

### 2.3 Naming Conventions
- **Files/Modules:** `lower_snake_case.py`.
- **Variables, functions, arguments:** `lower_snake_case`.
- **Classes:** `UpperCamelCase`.
- **Constants:** `ALL_CAPS_WITH_UNDERSCORES`.
- Avoid ambiguous names (`l`, `O`, `I`).

### 2.4 Documentation & Comments
- Each file, function, class, method should have a docstring describing its purpose, inputs, outputs, and side effects.
- Use [PEP 257](https://peps.python.org/pep-0257/) for docstring formatting.
- Block comments begin with `# `, inline comments use two spaces from code, and are only for non-trivial logic.

### 2.5 Error Handling
- Catch specific exceptions only (not bare `except:`).
- Provide actionable error messages in exception handlers.
- When raising an error, use `raise ValueError("message")` with informative text.
- Exit scripts with non-zero status on fatal errors—print messages to stderr.

### 2.6 Typing & Modern Features
- Prefer [type hinting](https://docs.python.org/3/library/typing.html) for all function signatures and variables in new/modified code.
- Use f-strings for string formatting (`f"Result: {val:.2f}"`).
- Use list comprehensions and generator expressions where clear.
- Avoid complex, deeply nested logic; refactor to small, testable functions.

### 2.7 Imports for Data/Reports
- Place data loading/writing code in `data/`, report output in `reports/`.
- Do not hardcode dataset/report file names—pass from config or arguments.

### 2.8 Scripting & Automation
- All scripts should provide a descriptive CLI interface using [argparse](https://docs.python.org/3/library/argparse.html) or [typer](https://typer.tiangolo.com/).
- Default behavior: print help message if arguments missing.
- Log progress using the `logging` module (not print), and set log level via CLI arg or config where possible.
- Main script entrypoint must be guarded by `if __name__ == "__main__":`
- Scripts should be stateless and deterministic (no reliance on global mutable state).

### 2.9 HTML Report Generation
- Reports should use clear file/section naming and save all static assets in `/reports/figures`.
- HTML output must be valid and self-contained, viewable with standard browsers.
- Optionally summarize report output to console/log upon script completion.

### 2.10 Agentic Code Rules
- Every new module/script must supply docstrings at file and function level suitable for agentic code editing.
- Never introduce secret keys or passwords into repo code or config.
- Always keep workflow and code clear, modularized, and easily testable. Add a simple README or usage in the module docstring when applicable.

---

## 3. Additional Agent Workflow Guidelines

- All code must pass `flake8` and if used, `black`/`isort` formatting.
- Every pull request must include test evidence (screenshots, logs, maintained test scripts, or instructions for manual report validation).
- If adding or modifying report-generating scripts, update/extend this AGENTS.md as needed for new conventions.
- If external rules occur in `.cursor/rules/` or `.github/copilot-instructions.md`, always summarize and incorporate them here.

---

_Last updated: 2026-02-23.  Review for new project-specific rules after initial setup or as the codebase evolves._
