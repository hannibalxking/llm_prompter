# promptbuilder/config/schema.py

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal

class TabConfig(BaseModel):
    title: str = "New Project"
    directory: Optional[str] = None
    # Add other tab-specific settings if needed (e.g., last used filters)

class SnippetCategory(BaseModel):
    items: Dict[str, str] = Field(default_factory=dict) # Name -> Snippet Text

class AppConfig(BaseModel):
    tabs: List[TabConfig] = Field(default_factory=list)
    window_geometry: Optional[bytes] = None # Store QMainWindow.saveGeometry() as bytes
    window_state: Optional[bytes] = None    # Store QMainWindow.saveState() as bytes
    theme: str = "AUTO" # AUTO, LIGHT, DARK
    # --- NEW: Token Counter Settings ---
    token_counter_backend: Literal["openai", "gemini"] = "openai"
    token_counter_model_openai: str = "cl100k_base"  # Default encoding for OpenAI
    token_counter_model_gemini: str = "gemini-1.5-flash"  # Default model for Gemini
    max_context_tokens: int = 8192 # Increased default?
    ignore_patterns: List[str] = Field(default_factory=lambda: [
        # Version control
        ".git", ".svn", ".hg",
        # IDE/Editor config
        ".idea", ".vscode", "*.sublime-project", "*.sublime-workspace", ".project", ".settings",
        # Python specific
        "__pycache__", "*.pyc", "*.pyo", "*.pyd",
        "*.egg-info", ".pytest_cache", ".mypy_cache",
        # Virtual environments
        "venv", ".venv", "env", ".env", "ENV", "VENV",
        # Build artifacts / Distribution
        "build", "dist", "node_modules", "target", "*.o", "*.so", "*.a", "*.lib", "*.dll", "*.exe",
        # OS specific
        ".DS_Store", "Thumbs.db",
        # Log files
        "*.log",
    ])
    # Store snippet definitions here or load from separate file/plugins
    prompt_snippets: Dict[str, SnippetCategory] = Field(default_factory=lambda: {
        "Objective": SnippetCategory(items={
            "Split File": (
                "Your task is to make a file drastically smaller by splitting it into more files. \n"
                "1. The goal is to get atomic scripts with a super strict separation of concerns. \n"
                "2. Make sure not to break the existing logic. Your job is not to change the logic, but to maintain it. \n"
                "3. If it makes sense to create new directories, include them in the file/module paths. \n"
                "4. Keep an eye on potential circular imports that might arise with the refactor. Avoid them. \n"
                "5. If you have to split up classes or large functions to achieve your goal, do it, but be careful to not break the logic. \n"
                "6. If you create new files, make sure these are not large either. No file should be larger than 200 lines of code. \n"
            ),
            "Custom": "" # Placeholder for custom input
        }),
        "Scope": SnippetCategory(items={
             "Custom": ""
        }),
        "Requirements": SnippetCategory(items={
            "Custom": ""
        }),
        "Constraints": SnippetCategory(items={
            "Custom": ""
        }),
        "Process": SnippetCategory(items={
            "Custom": ""
        }),
        "Output": SnippetCategory(items={
            # --- XML Diff Prompt ---
            "XML Diff": (
                "Strict Output Format for Code Changes (XML):\n"
                "Generate only the absolute minimum code changes necessary to fulfill the request. Do not refactor unrelated code or introduce unnecessary modifications.\n\n" 
                "If you suggest code modifications, you MUST provide the changes for EACH modified file in the following TWO formats, enclosed within the specified XML tags.\n\n"
                "CRITICAL REQUIREMENTS:\n"
                "1.  CDATA FORMATTING: Preserve ALL original newline characters (`\\n`) within the CDATA sections for BOTH the diff and the proposed content. Do NOT collapse content into a single line.\n"
                "2.  CDATA FORMATTING: The content inside CDATA MUST be multi-line and verbatim, exactly matching the standard unified diff format or the final file content.\n"
                "3.  CORRECT PATH: Ensure the `file` attribute contains the correct path relative to the project root, using forward slashes (e.g., `src/module/file.py`).\n"
                "4.  CORRECT XML STRUCTURE: Provide BOTH the `<diff>` block closing with </diff> AND the `<proposed_content>` block closing with </proposed_content> for EVERY modified file.\n"
                "5.  CORRECT DIFF AND PROPOSED_CONTENT: Make absolutely sure the diff contains all the changes made, and the proposed_content block is identical to the source file apart from the modifications outlined in the diff.\n"
                "6.  NEW FILES: When suggesting new files, prepare their diffs and proposed content in the same way as for existing files.\n"
                "7.  EXPLANATIONS: Always explain the changes to a file in max 2 sentences below the two XML blocks.\n"
                "Failure to meet these requirements, especially newline preservation, will render the output INVALID and unusable.\n\n"
                "--- Format Specification ---\n"
                "A.  **Unified Diff Block:**\n"
                "    -   Tag: `<diff file=\"path/relative/to/root.py\">`\n"
                "    -   Content: Standard multi-line unified diff text (minimal changes only).\n" 
                "    -   Wrapper: The multi-line diff text MUST be enclosed in `<![CDATA[...]]>`.\n"
                "    -   Example:\n"
                "      <diff file=\"src/utils.py\">\n"
                "      <![CDATA[\n"
                "      --- a/src/utils.py\n" 
                "      +++ b/src/utils.py\n" 
                "      @@ -10,3 +10,4 @@\n" 
                "       def helper_function():\n" 
                "           # Old code\n" 
                "      +    # New code added\n" 
                "           pass\n" 
                "      ]]>\n"
                "      </diff>\n\n"
                "B.  **Complete Proposed File Content Block:**\n"
                "    -   Tag: `<proposed_content file=\"path/relative/to/root.py\">`\n"
                "    -   Content: The *entire* proposed multi-line content of the file after applying the minimal changes.\n" 
                "    -   Wrapper: The full multi-line file content MUST be enclosed in `<![CDATA[...]]>`.\n"
                "    -   Example:\n"
                "      <proposed_content file=\"src/utils.py\">\n"
                "      <![CDATA[\n" 
                "      # The complete proposed content of src/utils.py after changes...\n" 
                "      import os\n\n"
                "      def helper_function():\n" 
                "          # New code added\n" 
                "          pass\n" 
                "      # ... rest of the file ...\n" 
                "      ]]>\n"
                "      </proposed_content>\n\n"
                "C.  **Short Explanation In Two Sentences**\n"
                "Follow this format exactly for every file. Maintain every line break within CDATA. Provide only minimal changes."
            ),
            # --- JSON Diff Prompt ---
            "JSON Diff": (
                "Strict Output Format for Code Changes (JSON):\n"
                "Generate only the absolute minimum code changes necessary to fulfill the request. Do not refactor unrelated code or introduce unnecessary modifications.\n\n" # <-- ADDED MINIMALITY INSTRUCTION
                "If you suggest code modifications, you MUST provide the changes as a single JSON array. Each object in the array represents ONE modified file and MUST have the following keys:\n"
                "1.  `file`: (String) The path relative to the project root, using forward slashes (e.g., \"src/module/file.py\").\n"
                "2.  `diff`: (String) The standard multi-line unified diff text representing the minimal changes. All newline characters MUST be preserved and properly escaped within the JSON string (e.g., \"\\n\").\n" # Added note
                "3.  `proposed_content`: (String) The complete, multi-line proposed content of the entire file after applying the minimal changes. All newline characters MUST be preserved and properly escaped within the JSON string (e.g., \"\\n\").\n\n" # Added note
                "CRITICAL REQUIREMENTS:\n"
                "- Output ONLY the JSON array. Do NOT include any explanatory text before or after the JSON itself. If you must use markdown, enclose the JSON array within a single ```json ... ``` block.\n"
                "- Ensure the JSON is valid.\n"
                "- Provide ALL THREE keys (`file`, `diff`, `proposed_content`) for EVERY object in the array.\n"
                "- Preserve all newlines using `\\n` within the string values.\n\n"
                "Example JSON Output:\n"
                "```json\n"
                "[\n"
                "  {\n"
                "    \"file\": \"src/utils.py\",\n"
                "    \"diff\": \"--- a/src/utils.py\\n+++ b/src/utils.py\\n@@ -10,3 +10,4 @@\\n def helper_function():\\n     # Old code\\n+    # New code added\\n     pass\\n\",\n"
                "    \"proposed_content\": \"# The complete proposed content of src/utils.py after changes...\\nimport os\\n\\ndef helper_function():\\n    # New code added\\n    pass\\n# ... rest of the file ...\\n\"\n"
                "  },\n"
                "  {\n"
                "    \"file\": \"main.py\",\n"
                "    \"diff\": \"--- a/main.py\\n+++ b/main.py\\n@@ ... diff content ...\",\n"
                "    \"proposed_content\": \"#!/usr/bin/env python\\n# ... full content of main.py ...\"\n"
                "  }\n"
                "]\n"
                "```\n"
                "Adhere strictly to this JSON format. Provide only minimal changes." # Added reminder
            ),
            # --- Markdown Diff Prompt ---
            "MD Diff": (
                "Strict Output Format for Code Changes (Markdown):\n"
                "Generate only the absolute minimum code changes necessary to fulfill the request. Do not refactor unrelated code or introduce unnecessary modifications.\n\n" # <-- ADDED MINIMALITY INSTRUCTION
                "If you suggest code modifications, you MUST provide the changes for EACH modified file using Markdown fenced code blocks with specific info strings as follows:\n\n"
                "1.  **Unified Diff Block:**\n"
                "    -   Start the block with exactly: ```diff file=\"path/relative/to/root.py\"\n"
                "    -   Inside the block: Provide the standard multi-line unified diff text representing the minimal changes.\n" # Added note
                "    -   End the block with: ```\n"
                "    -   Example:\n"
                "      ```diff file=\"src/utils.py\"\n"
                "      --- a/src/utils.py\n"
                "      +++ b/src/utils.py\n"
                "      @@ -10,3 +10,4 @@\n"
                "       def helper_function():\n"
                "           # Old code\n"
                "      +    # New code added\n"
                "           pass\n"
                "      ```\n\n"
                "2.  **Complete Proposed File Content Block:**\n"
                "    -   Start the block with exactly: ```python file=\"path/relative/to/root.py\" type=\"proposed\"\n"
                "    -   Inside the block: Provide the *entire* proposed multi-line content of the file after applying the minimal changes.\n" # Added note
                "    -   End the block with: ```\n"
                "    -   Example:\n"
                "      ```python file=\"src/utils.py\" type=\"proposed\"\n"
                "      # The complete proposed content of src/utils.py after changes...\n"
                "      import os\n\n"
                "      def helper_function():\n"
                "          # New code added\n"
                "          pass\n"
                "      # ... rest of the file ...\n"
                "      ```\n\n"
                "CRITICAL REQUIREMENTS:\n"
                "- Provide BOTH blocks (diff and proposed) consecutively for EVERY modified file.\n"
                "- The `file=\"...\"` attribute MUST contain the correct path relative to the project root, using forward slashes.\n"
                "- Preserve ALL original newline characters and indentation within the code blocks. Do NOT collapse content.\n"
                "- Output ONLY these fenced code blocks. Do NOT include any other explanatory text unless specifically requested.\n\n"
                "Follow this format exactly. Provide only minimal changes." # Added reminder
            ),
            "Full and Final": "Give me the full and final scripts you added or modified (without diff/proposed_content tags unless a Diff format is also selected). Must be production-ready.",
            "Custom": ""
        })
    })
    common_questions: List[str] = Field(default_factory=lambda: [
        "What is one thing you would change/improve if you could and why?",
        "Is this solution lacking? What is missing?",
        "Do you see opportunities to improve the structure?"
    ])
    # Add other global settings: secrets patterns, etc.
    secret_patterns: List[str] = Field(default_factory=lambda: [
        # More specific patterns with length and character set constraints
        # Example: AWS Access Key ID (AKIA...)
        r"\b(AKIA[0-9A-Z]{16})\b",
        # Fixes high-priority issue #5: AWS Secret Key Regex Accuracy
        # Look for common assignment keywords/chars before the key
        r"(aws_secret_access_key|secret_access_key|SecretAccessKey|AWS_SECRET_ACCESS_KEY)[\s:=]+['\"]?([a-zA-Z0-9/+=]{40})['\"]?",
        # Example: Generic API Key (alphanumeric, > 20 chars) - adjust length/chars as needed
        r"api[_-]?key[\s:=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?",
        # Example: Generic Secret (alphanumeric, > 16 chars)
        r"secret[\s:=]+['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
        # Example: Private Key Block Headers
        r"-----BEGIN (RSA|OPENSSH|EC|PGP) PRIVATE KEY-----",
    ])