# promptbuilder/plugins/git_diff.py
import subprocess
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from ..core.plugins import ContextProvider, register_plugin
from ..core.models import ContextResult, ContextFile
from ..config.loader import get_config # Import config loader
from ..core.token_counter import UnifiedTokenCounter # Use unified counter

@register_plugin # Register this plugin automatically if this module is imported
class GitDiffProvider(ContextProvider):
    name: str = "git_diff" # Unique name for this provider

    def get_context(self, options: Dict | None = None) -> ContextResult:
        """Generates context from `git diff` output."""
        logger.info("GitDiffProvider: Generating context...")
        options = options or {}
        repo_path_str = options.get("repo_path", ".") # Get repo path from options
        repo_path = Path(repo_path_str).resolve()
        staged = options.get("staged", False) # Option for `git diff --staged`

        if not (repo_path / ".git").is_dir():
            logger.error(f"GitDiffProvider: Path '{repo_path}' is not a git repository.")
            return ContextResult(
                context_xml="<context><error>Not a git repository</error></context>",
                included_files=[], skipped_files=[], total_tokens=0, budget_details="Error"
            )

        command = ["git", "diff"]
        if staged:
            command.append("--staged")

        try:
            # Use shell=True on Windows if git might be a .cmd or .bat file,
            # but generally safer to rely on it being in PATH directly.
            process = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace', # Handle potential decoding errors
                check=False, # Don't raise exception on non-zero exit code
                shell=False # Avoid shell=True unless necessary
            )

            if process.returncode != 0:
                error_msg = process.stderr.strip() or f"Git command failed with code {process.returncode}"
                logger.error(f"GitDiffProvider: {error_msg}")
                # Escape error message for XML
                import html
                safe_error_msg = html.escape(error_msg)
                return ContextResult(
                    context_xml=f"<context><error>Git diff failed: {safe_error_msg}</error></context>",
                    included_files=[], skipped_files=[], total_tokens=0, budget_details="Git Error"
                )

            diff_content = process.stdout
            if not diff_content.strip():
                 diff_content = "<no changes detected>"
                 logger.info("GitDiffProvider: No changes detected.")


            # --- Format as XML ---
            # Treat the entire diff as one "file" for simplicity
            file_name = "git_diff_staged.diff" if staged else "git_diff_unstaged.diff"
            # Get token counter settings from config
            config = get_config()
            # Instantiate counter and count tokens
            token_counter = UnifiedTokenCounter(backend=config.token_counter_backend, model_name=config.token_counter_model_openai if config.token_counter_backend == "openai" else config.token_counter_model_gemini)
            tokens = token_counter.count(diff_content)
            # Basic escaping
            import html
            escaped_content = html.escape(diff_content)
            safe_name = html.escape(file_name, quote=True)
            safe_path = html.escape(repo_path_str, quote=True)

            context_xml = (
                "<context>\n"
                f"    <file name='{safe_name}' path='{safe_path}' status='generated' tokens='{tokens}'>\n"
                f"{escaped_content}\n"
                "    </file>\n"
                "</context>"
            )

            # Create a ContextFile representation
            diff_file = ContextFile(
                path=repo_path / file_name, # Pseudo path
                content=diff_content,
                tokens=tokens,
                status="generated"
            )

            logger.info(f"GitDiffProvider: Generated diff context ({tokens} tokens).")
            return ContextResult(
                context_xml=context_xml,
                included_files=[diff_file],
                skipped_files=[],
                total_tokens=tokens,
                budget_details="Git diff generated"
            )

        except FileNotFoundError:
            logger.error("GitDiffProvider: 'git' command not found. Is Git installed and in PATH?")
            return ContextResult(
                context_xml="<context><error>Git command not found</error></context>",
                included_files=[], skipped_files=[], total_tokens=0, budget_details="Git Error"
            )
        except Exception as e:
            logger.exception(f"GitDiffProvider: Unexpected error: {e}")
            import html
            safe_error = html.escape(str(e))
            return ContextResult(
                context_xml=f"<context><error>Unexpected error: {safe_error}</error></context>",
                included_files=[], skipped_files=[], total_tokens=0, budget_details="Error"
            )

    @classmethod
    def get_options_schema(cls) -> Dict | None:
        # Example: Define options users might set in UI or CLI
        return {
            "repo_path": {"type": "string", "default": ".", "description": "Path to the git repository."},
            "staged": {"type": "boolean", "default": False, "description": "Show staged changes instead of unstaged."}
        }