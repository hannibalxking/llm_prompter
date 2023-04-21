# promptbuilder/cli/snippet_handler.py

from typing import Dict, Set, Optional, Any, Tuple
from loguru import logger

from ..config.schema import AppConfig

def process_snippet_args(cli_args: Dict[str, Any], config: AppConfig) -> Tuple[Dict[str, Dict[str, Optional[str]]], Set[str]]:
    """
    Processes CLI arguments related to prompt snippets and questions.

    Args:
        cli_args: Dictionary of arguments from the Typer command (e.g., locals()).
        config: The loaded AppConfig object.

    Returns:
        A tuple containing:
        - selected_snippets_cli: Dict[str, Dict[str, Optional[str]]] - {Category: {Name: CustomText}}
        - selected_questions_cli: Set[str] - Set of selected question texts.
    """
    selected_snippets_cli: Dict[str, Dict[str, Optional[str]]] = {}
    snippet_map = { # Map CLI flags to config keys and custom text args
        "objective": ("Objective", "objective_custom"),
        "scope": ("Scope", "scope_custom"),
        "requirements": ("Requirements", "requirements_custom"),
        "constraints": ("Constraints", "constraints_custom"),
        "process": ("Process", "process_custom"),
        "output_format": ("Output", "output_format_custom"), # Map CLI flag to config key
    }

    for flag_name, (config_key, custom_text_arg_name) in snippet_map.items():
        selected_names = cli_args.get(flag_name)
        if selected_names:
            category_data = config.prompt_snippets.get(config_key)
            if category_data is None:
                 logger.warning(f"Snippet category '{config_key}' not found in configuration. Skipping flag '--{flag_name}'.")
                 continue
            category_items = category_data.items

            valid_selections: Dict[str, Optional[str]] = {}
            for name in selected_names:
                if name == "Custom":
                    custom_text = cli_args.get(custom_text_arg_name)
                    if custom_text: valid_selections["Custom"] = custom_text
                    else: logger.warning(f"'--{flag_name} Custom' used but '--{custom_text_arg_name}' not provided. Ignoring Custom.")
                elif name in category_items: valid_selections[name] = None
                else: logger.warning(f"Invalid snippet name '{name}' for category '{config_key}'. Ignoring.")
            if valid_selections: selected_snippets_cli[config_key] = valid_selections

    selected_questions_cli: Set[str] = set()
    question_arg = cli_args.get("question")
    if question_arg:
        valid_questions = {q for q in question_arg if q in config.common_questions}
        invalid_questions = set(question_arg) - valid_questions
        if invalid_questions: logger.warning(f"Ignoring invalid questions: {invalid_questions}")
        selected_questions_cli.update(valid_questions)

    return selected_snippets_cli, selected_questions_cli