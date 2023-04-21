# promptbuilder/core/prompt_engine.py
from typing import Dict, Set, Optional
from loguru import logger

from ..config.loader import get_config

class PromptEngine:
    """Builds the <instructions> part of the prompt."""

    def __init__(self):
        # Load snippet definitions (could be passed in or loaded from config)
        self.config = get_config()
        self.snippet_definitions = self.config.prompt_snippets
        self.common_questions_list = self.config.common_questions
        logger.debug("PromptEngine initialized.")

    def build_instructions_xml(
        self,
        selected_snippets: Dict[str, Dict[str, Optional[str]]], # {Category: {Name: CustomText}}
        selected_questions: Set[str]
    ) -> str:
        """Generates the <instructions> XML block."""
        lines = []
        lines.append("<instructions>")

        # Order categories based on config definition order (or alphabetical)
        category_order = list(self.snippet_definitions.keys())

        # 1) Normal snippet categories
        for category in category_order:
            if category not in selected_snippets:
                continue

            items_chosen = selected_snippets[category]
            if not items_chosen:
                continue

            # Use lowercase tag name, handle spaces if needed (e.g., replace with _)
            cat_lower = category.lower().replace(" ", "_")
            lines.append(f"    <{cat_lower}>")

            # Order items within category (e.g., definition order or alpha)
            # For simplicity, using the order they appear in the input dict here
            for item_name, custom_text in items_chosen.items():
                if item_name == "Custom" and custom_text:
                    # Indent custom text properly, handle multi-line
                    indented_text = "\n".join(f"        {line}" for line in custom_text.strip().splitlines())
                    lines.append(indented_text)
                elif item_name != "Custom":
                    # Look up the standard snippet text
                    try:
                        snippet_text = self.snippet_definitions[category].items[item_name]
                        if snippet_text: # Ensure snippet text exists
                             lines.append(f"        {snippet_text}")
                        else:
                             logger.warning(f"Empty snippet text for {category}/{item_name}")
                    except KeyError:
                        logger.error(f"Definition missing for snippet: {category}/{item_name}")

            lines.append(f"    </{cat_lower}>")

        # 2) Additional questions
        if selected_questions:
            lines.append("    <questions>")
            # Ensure consistent order for questions
            for qtext in self.common_questions_list:
                if qtext in selected_questions:
                    lines.append(f"        {qtext}")
            lines.append("    </questions>")

        lines.append("</instructions>")
        logger.debug(f"Generated instructions block with {len(lines)} lines.")
        return "\n".join(lines)