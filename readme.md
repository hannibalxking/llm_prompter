# PromptBuilder

A slick prompt-crafting workbench for developers.

Point it at one or more repos, tick the files or folders you care about, and pick prompt “snippets” (objective, scope, constraints, etc.) from a side panel. It generates reproducible, high-signal prompts for LLMs, helping you manage context windows and reduce copy-paste friction.

## Features

*   Select files/folders from local repositories using glob patterns or UI tree.
*   Choose pre-defined or custom prompt instruction snippets.
*   Asynchronous file scanning and token counting in GUI.
*   Live word, character, and token counts (using `tiktoken`).
*   Context budgeting (truncation strategy).
*   XML-structured output (`<instructions>` and `<context>`).
*   Plugin system for custom context providers (e.g., git diffs).
*   CLI for headless operation with include/exclude patterns.
*   Dark/Light theme toggle.

## Installation & Running

**Prerequisites:**

*   Python 3.10+ (due to use of `|` type unions)
*   Poetry (for development/installation from source)

**From Source (Development):**

1.  Clone the repository:
    ```bash
    git clone <your-repo-url>
    cd promptbuilder
    ```
2.  Install dependencies:
    ```bash
    poetry install --with dev --extras "cli" # Include CLI and dev dependencies
    ```
3.  Run the application:
    ```bash
    poetry run python -m promptbuilder.main
    ```
4.  Run the CLI (example):
    ```bash
    # Build prompt from current dir, include only python files, exclude tests, save to my_prompt.xml
    poetry run promptbuilder-cli build --repo . --include "**/*.py" --exclude "**/test_*" -o my_prompt.xml --objective Review --scope High-level
    ```

**Building an Executable (using PyInstaller):**

(Requires PyInstaller: `pip install pyinstaller`)

1.  Ensure the `scripts/freeze.spec` file is configured correctly (e.g., paths, included data). A template is provided.
2.  Build using the spec file (run from the project root):
    ```bash
    # Ensure you are in the project root directory
    poetry run pyinstaller scripts/freeze.spec
    ```
    The executable will be in the `dist/PromptBuilder` directory. Use the `scripts/build.sh` (or `.bat`) helper script for convenience.

## Contributing

1.  Install development dependencies: `poetry install --with dev --extras "cli"`
2.  Set up pre-commit hooks: `poetry run pre-commit install`
3.  Follow coding style (Black, Ruff) and type hints (mypy). Target Python 3.10+.
4.  Write tests for new features, especially for core logic and utilities.
5.  Run tests: `poetry run pytest`
6.  Run linters: `poetry run pre-commit run --all-files`

## Project Structure

(See the detailed plan in the initial request - core logic is UI-agnostic, thin Qt layer on top)

## Plugin System

PromptBuilder allows extending context sources via plugins.

**How it Works:**

*   Plugins are discovered using Python's entry points mechanism, specifically the `promptbuilder.context_providers` group.
*   A context provider plugin is a Python class that inherits from `promptbuilder.core.plugins.ContextProvider`.
*   It must implement the `get_context(self, options: dict | None = None) -> ContextResult` method.
*   It must define a unique `name: str` class attribute.

**Example Plugin (`my_plugin/my_provider.py`):**

```python
# my_plugin/my_provider.py
from promptbuilder.core.plugins import ContextProvider, register_plugin
from promptbuilder.core.models import ContextResult, ContextFile
from promptbuilder.core.token_counter import count_tokens
import html

# Option 1: Use decorator (if module is imported somehow)
# @register_plugin
# class MyDataProvider(ContextProvider):
#     name: str = "my_data_source"
#     ...

# Option 2: Rely on entry point discovery (preferred for external plugins)
class MyDataProvider(ContextProvider):
    name: str = "my_data_source" # Unique name used in UI/CLI

    def get_context(self, options: dict | None = None) -> ContextResult:
        # Example: Read data from a specific file mentioned in options
        options = options or {}
        file_path = options.get("source_file", "default_data.txt")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            status = "generated"
        except Exception as e:
            content = f"<Error reading {file_path}: {html.escape(str(e))}>"
            status = "error"

        tokens = count_tokens(content)
        safe_name = html.escape(self.name, quote=True)
        safe_path = html.escape(file_path, quote=True)
        escaped_content = html.escape(content)

        context_xml = (
            "<context>\n"
            f"    <file name='{safe_name}' path='{safe_path}' status='{status}' tokens='{tokens}'>\n"
            f"{escaped_content}\n"
            "    </file>\n"
            "</context>"
        )

        return ContextResult(
            context_xml=context_xml,
            included_files=[ContextFile(path=Path(file_path), content=content, tokens=tokens, status=status)],
            skipped_files=[],
            total_tokens=tokens,
            budget_details=f"{self.name} generated"
        )

    @classmethod
    def get_options_schema(cls) -> dict | None:
        # Optional: Define configuration options for this provider
        return {
            "source_file": {"type": "string", "default": "default_data.txt", "description": "Path to the data file."}
        }