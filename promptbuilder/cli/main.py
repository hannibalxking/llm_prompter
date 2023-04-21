# promptbuilder/cli/main.py

from pathlib import Path
from typing import Optional, List

import typer
from loguru import logger

# --- Setup logging early ---
from ..services.logging import setup_logging
# Logging setup is deferred until callback

# --- Import core components ---
from ..config.loader import get_config
from ..core.fs_scanner import _FileScannerCore
from ..core.prompt_engine import PromptEngine
from ..core.context_assembler import _ContextAssemblerCore
from .. import __version__

# --- Import CLI specific components ---
from .filters import _filter_nodes, _collect_paths_from_nodes
from .snippet_handler import process_snippet_args

# Plugins are loaded via promptbuilder/__init__.py

# --- Typer App ---
app = typer.Typer(help="PromptBuilder CLI - Generate prompts headlessly (Windows).")

def version_callback(value: bool):
    """Callback to show version and exit."""
    if value:
        print(f"PromptBuilder CLI Version: {__version__}")
        raise typer.Exit()

@app.callback()
def main_options(
    ctx: typer.Context,
    verbose: bool = typer.Option(True, "--verbose", "-v", help="Enable debug logging."),
    version: Optional[bool] = typer.Option(None, "--version", callback=version_callback, is_eager=True, help="Show version and exit."),
):
    """Main callback to set up logging."""
    log_level = "DEBUG" if verbose else "INFO"
    # Configure logging here, after flags are parsed
    setup_logging(level=log_level, verbose=verbose)
    logger.info(f"Log level set to: {log_level}")
    ctx.ensure_object(dict)
    ctx.obj["VERBOSE"] = verbose


@app.command()
def build(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the repository root.", exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True),
    include: Optional[List[str]] = typer.Option(None, "--include", "-i", help="Glob patterns for files/folders to include (relative to repo root, e.g., 'src/**/*.py', '*.md')."),
    exclude: Optional[List[str]] = typer.Option(None, "--exclude", "-e", help="Glob patterns for files/folders to exclude (applied after includes, e.g., '**/test_*', 'docs/')."),
    output: Path = typer.Option("prompt.xml", "--output", "-o", help="Output file path for the generated prompt.", writable=True, resolve_path=True),
    # Snippet selection flags (passed to snippet_handler)
    objective: Optional[List[str]] = typer.Option(None, "--objective", help="Objective snippet name(s) (e.g., 'Review', 'Develop'). Use 'Custom' for custom text."),
    objective_custom: Optional[str] = typer.Option(None, "--objective-custom", help="Custom text if '--objective Custom' is used."),
    scope: Optional[List[str]] = typer.Option(None, "--scope", help="Scope snippet name(s)."),
    scope_custom: Optional[str] = typer.Option(None, "--scope-custom", help="Custom text if '--scope Custom' is used."),
    requirements: Optional[List[str]] = typer.Option(None, "--requirements", help="Requirements snippet name(s)."),
    requirements_custom: Optional[str] = typer.Option(None, "--requirements-custom", help="Custom text if '--requirements Custom' is used."),
    constraints: Optional[List[str]] = typer.Option(None, "--constraints", help="Constraints snippet name(s)."),
    constraints_custom: Optional[str] = typer.Option(None, "--constraints-custom", help="Custom text if '--constraints Custom' is used."),
    process: Optional[List[str]] = typer.Option(None, "--process", help="Process snippet name(s)."),
    process_custom: Optional[str] = typer.Option(None, "--process-custom", help="Custom text if '--process Custom' is used."),
    output_format: Optional[List[str]] = typer.Option(None, "--output-format", help="Output format snippet name(s)."),
    output_format_custom: Optional[str] = typer.Option(None, "--output-format-custom", help="Custom text if '--output-format Custom' is used."),
    question: Optional[List[str]] = typer.Option(None, "--question", help="Additional question(s) to include (full text)."),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Override maximum context tokens."),
):
    """
    Builds a prompt by scanning a repository and selecting snippets via CLI flags.
    """
    logger.info(f"Building prompt for repository: {repo}")
    logger.info(f"Output will be saved to: {output}")

    config = get_config() # Load config to get ignore patterns, snippet defs
    engine = PromptEngine() # Uses loaded config

    # --- Scan Repository (using sync core scanner) ---
    logger.info("Scanning repository...")
    # Pass repo path and ignore patterns to the scanner core instance
    scanner = _FileScannerCore(root_path=repo, ignore_patterns=config.ignore_patterns)
    try:
        # Run the synchronous scan
        root_nodes = scanner.scan_directory_sync()
        if not root_nodes:
             logger.error("Scan returned no files or directories. Check path and permissions.")
             raise typer.Exit(code=1)
        # We expect only one root node from the scan
        scanned_nodes = root_nodes[0].children # Get children of the root repo node
    except ValueError as e:
         logger.error(f"Scan Error: {e}")
         raise typer.Exit(code=1)
    except Exception as e:
        logger.exception(f"Unexpected error during repository scan: {e}")
        raise typer.Exit(code=1)

    logger.info(f"Scan complete. Found {len(scanned_nodes)} top-level items initially.")

    # --- Filter scanned nodes based on include/exclude patterns ---
    selected_nodes_flat = _filter_nodes(scanned_nodes, repo, include, exclude) # Use imported function

    # --- Extract file paths from selected nodes ---
    # Pass the flat list of kept nodes (including directories) to collect leaf files
    selected_paths = _collect_paths_from_nodes(selected_nodes_flat)

    if not selected_paths:
         logger.error("No files selected after applying include/exclude patterns. Aborting.")
         raise typer.Exit(code=1)
    logger.info(f"Selected {len(selected_paths)} files for context.")

    # --- Determine selected snippets (using snippet_handler) ---
    cli_args = locals() # Get local variables dict to pass to handler
    selected_snippets_cli, selected_questions_cli = process_snippet_args(cli_args, config)

    # --- Build Instructions ---
    logger.debug(f"Selected Snippets: {selected_snippets_cli}")
    logger.debug(f"Selected Questions: {selected_questions_cli}")
    instructions_xml = engine.build_instructions_xml(selected_snippets_cli, selected_questions_cli)

    # --- Assemble Context (using sync core assembler) ---
    logger.info("Assembling context...")
    context_max_tokens = max_tokens if max_tokens is not None else config.max_context_tokens
    assembler = _ContextAssemblerCore(project_root_path=repo, secret_patterns=config.secret_patterns) # Pass project root
    try:
        context_result = assembler.assemble_context_sync(selected_paths, context_max_tokens)
    except Exception as e:
        logger.exception(f"Error assembling context: {e}")
        raise typer.Exit(code=1)

    # --- Combine and Save ---
    final_prompt = instructions_xml + "\n\n" + context_result.context_xml
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(final_prompt, encoding='utf-8')
        logger.success(f"Prompt successfully written to: {output}")
        logger.info(f"Final Token Count: {context_result.total_tokens}/{context_max_tokens}")
        if context_result.budget_details: logger.info(f"Context Budget Note: {context_result.budget_details}")
        if context_result.skipped_files: logger.warning(f"Skipped {len(context_result.skipped_files)} files due to budget or errors.")

    except Exception as e:
        logger.exception(f"Error writing output file: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()