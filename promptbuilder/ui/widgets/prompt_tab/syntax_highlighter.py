# promptbuilder/ui/widgets/prompt_tab/syntax_highlighter.py

import re
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression # Use Qt's regex for potential performance benefits

class PythonHighlighter(QSyntaxHighlighter):
    """
    A syntax highlighter for Python code and embedded XML tags within a QTextDocument.

    Uses regular expressions to identify keywords, operators, strings, numbers,
    comments, decorators, class/function definitions, XML elements, docstrings,
    and more, applying specific character formats (colors, styles).
    Handles multi-line strings/docstrings and skips Python/detailed XML
    highlighting within <instructions> blocks.
    """

    # --- Precompile Regex Patterns ---
    # Keywords
    _keywords = [
        'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
        'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from',
        'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not',
        'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
        'True', 'False', 'None'
    ]
    # Built-ins (common ones)
    _builtins = [
        'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes', 'callable',
        'chr', 'classmethod', 'compile', 'complex', 'delattr', 'dict', 'dir',
        'divmod', 'enumerate', 'eval', 'exec', 'filter', 'float', 'format',
        'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex',
        'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len',
        'list', 'locals', 'map', 'max', 'memoryview', 'min', 'next', 'object',
        'oct', 'open', 'ord', 'pow', 'print', 'property', 'range', 'repr',
        'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod',
        'str', 'sum', 'super', 'tuple', 'type', 'vars', 'zip', '__import__'
    ]
    # Operators
    _operators = [
        '=', '==', '!=', '<', '<=', '>', '>=',
        '\+', '-', '\*', '/', '//', '%', '\*\*',
        '\+=', '-=', '\*=', '/=', '%=', '\*\*\=',
        '&', '\|', '\^', '~', '<<', '>>',
    ]
    # Braces
    _braces = ['\{', '\}', '\(', '\)', '\[', '\]']

    # Special keywords like self/cls
    _self_cls = ['self', 'cls']

    def __init__(self, parent=None):
        """Initializes the highlighter and defines formatting rules."""
        super().__init__(parent)

        # --- Define Character Formats ---
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(255, 0, 255)) # Magenta
        keyword_format.setFontWeight(QFont.Weight.Bold)

        self_cls_format = QTextCharFormat()
        self_cls_format.setForeground(QColor(255, 0, 255)) # Magenta (same as keyword)

        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor(86, 156, 214)) # VS Code Blue/Cyan

        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor(180, 180, 180)) # Light Gray

        brace_format = QTextCharFormat()
        brace_format.setForeground(QColor(255, 255, 0)) # Yellow

        string_format = QTextCharFormat() # Format for regular single/double quoted strings
        string_format.setForeground(QColor(206, 145, 120)) # VS Code Orange

        # NEW: Docstring format (triple-quoted)
        self.docstring_format = QTextCharFormat()
        self.docstring_format.setForeground(QColor(106, 153, 85)) # VS Code Docstring Green

        number_format = QTextCharFormat()
        number_format.setForeground(QColor(181, 206, 168)) # VS Code Number Green

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor(0, 128, 0)) # Darker Green for comments
        self.comment_format.setFontItalic(True)

        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor(155, 155, 155)) # Gray

        definition_format = QTextCharFormat()
        definition_format.setForeground(QColor(78, 201, 176)) # VS Code Teal/Blue
        definition_format.setFontWeight(QFont.Weight.Bold)

        magic_method_format = QTextCharFormat()
        magic_method_format.setForeground(QColor(78, 201, 176)) # VS Code Teal/Blue (same as defs)

        # --- XML Specific Formats ---
        self.xml_tag_delim_format = QTextCharFormat() # <, >, />, </
        self.xml_tag_delim_format.setForeground(QColor(128, 128, 128)) # Gray for delimiters
        self.xml_tag_delim_format.setFontWeight(QFont.Weight.Bold)

        self.xml_tag_name_format = QTextCharFormat() # tag names like 'file', 'context'
        self.xml_tag_name_format.setForeground(QColor(86, 156, 214)) # Blue/Cyan like builtins
        self.xml_tag_name_format.setFontWeight(QFont.Weight.Bold)

        self.xml_attr_name_format = QTextCharFormat() # attribute names like 'name', 'module'
        self.xml_attr_name_format.setForeground(QColor(156, 220, 254)) # Lighter Blue

        self.xml_attr_value_format = QTextCharFormat() # attribute values like "'__init__.py'"
        self.xml_attr_value_format.setForeground(QColor(206, 145, 120)) # Orange like strings

        # --- Build Highlighting Rules (Order Matters!) ---
        # Store Python rules separately for conditional application
        self.python_highlighting_rules = []

        # Rule: Keywords
        keyword_patterns = [r'\b' + kw + r'\b' for kw in self._keywords]
        self.python_highlighting_rules.extend([(QRegularExpression(p), keyword_format) for p in keyword_patterns])

        # Rule: self, cls
        self_cls_patterns = [r'\b' + sc + r'\b' for sc in self._self_cls]
        self.python_highlighting_rules.extend([(QRegularExpression(p), self_cls_format) for p in self_cls_patterns])

        # Rule: Builtins
        builtin_patterns = [r'\b' + bi + r'\b' for bi in self._builtins]
        self.python_highlighting_rules.extend([(QRegularExpression(p), builtin_format) for p in builtin_patterns])

        # Rule: Operators
        self.python_highlighting_rules.extend([(QRegularExpression(op), operator_format) for op in self._operators])

        # Rule: Braces
        self.python_highlighting_rules.extend([(QRegularExpression(b), brace_format) for b in self._braces])

        # Rule: Decorators (@...)
        self.python_highlighting_rules.append((QRegularExpression(r'@[a-zA-Z_][a-zA-Z0-9_]*'), decorator_format))

        # Rule: Class/Function definition names (after 'class' or 'def')
        self.python_highlighting_rules.append((QRegularExpression(r'\b(class|def)\s+([a-zA-Z_][a-zA-Z0-9_]*)'), definition_format))

        # Rule: Magic Methods (__method__)
        self.python_highlighting_rules.append((QRegularExpression(r'\b(__\w+__)\b'), magic_method_format))

        # Rule: Numbers (integers, floats, hex, binary)
        self.python_highlighting_rules.append((QRegularExpression(r'\b[0-9]+[lL]?\b'), number_format))
        self.python_highlighting_rules.append((QRegularExpression(r'\b0[xX][0-9a-fA-F]+[lL]?\b'), number_format))
        self.python_highlighting_rules.append((QRegularExpression(r'\b0[bB][01]+[lL]?\b'), number_format))
        self.python_highlighting_rules.append((QRegularExpression(r'\b[0-9]+\.[0-9]*(e[+-]?[0-9]+)?\b'), number_format))
        self.python_highlighting_rules.append((QRegularExpression(r'\b\.[0-9]+(e[+-]?[0-9]+)?\b'), number_format))

        # Rule: Single-quoted strings ('...') - General Python strings (apply after XML attr values)
        self.python_highlighting_rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))
        # Rule: Double-quoted strings ("...") - General Python strings
        self.python_highlighting_rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))

        # Rule: Single-line comments (#...) - Apply last for single-line rules
        self.python_highlighting_rules.append((QRegularExpression(r'#[^\n]*'), self.comment_format))

        # --- Multi-line String/Docstring Rules (using block state) ---
        self.tri_double_start_expression = QRegularExpression(r'"""')
        self.tri_double_end_expression = QRegularExpression(r'"""')
        self.tri_single_start_expression = QRegularExpression(r"'''")
        self.tri_single_end_expression = QRegularExpression(r"'''")

        # --- Instruction Block Rules ---
        self.instruction_start_expression = QRegularExpression(r"<instructions>")
        self.instruction_end_expression = QRegularExpression(r"</instructions>")

        # Define block states (must be < 256)
        self.NORMAL_STATE = -1 # Default state
        self.IN_TRIPLE_DOUBLE_DOCSTRING = 1 # Changed state name
        self.IN_TRIPLE_SINGLE_DOCSTRING = 2 # Changed state name
        self.IN_INSTRUCTIONS = 3 # State for instruction block


    def highlightBlock(self, text):
        """Highlights a single block (line) of text."""
        # --- State Initialization ---
        start_index = 0
        prev_state = self.previousBlockState()
        current_processing_state = self.NORMAL_STATE # Track if we are inside Python, XML, or Instructions

        # --- Handle Previous Block State ---
        # Check if continuing a multi-line docstring
        if prev_state == self.IN_TRIPLE_DOUBLE_DOCSTRING:
            start_index = self.highlight_multiline(text, self.tri_double_end_expression, self.IN_TRIPLE_DOUBLE_DOCSTRING, 0, self.docstring_format)
            if start_index == -1: # Still in docstring
                return # Nothing else to process on this line
        elif prev_state == self.IN_TRIPLE_SINGLE_DOCSTRING:
            start_index = self.highlight_multiline(text, self.tri_single_end_expression, self.IN_TRIPLE_SINGLE_DOCSTRING, 0, self.docstring_format)
            if start_index == -1: # Still in docstring
                return
        # Check if continuing inside instructions block
        elif prev_state == self.IN_INSTRUCTIONS:
            match = self.instruction_end_expression.match(text, 0)
            if match.hasMatch():
                # Instruction block ends on this line
                end_index = match.capturedStart() + match.capturedLength()
                self.highlight_xml_tag(text, 0, end_index) # Highlight the closing tag
                self.setCurrentBlockState(self.NORMAL_STATE)
                start_index = end_index # Start normal processing after the tag
            else:
                # Still inside instructions, only highlight XML tags
                self.setCurrentBlockState(self.IN_INSTRUCTIONS)
                self.highlight_xml_details(text, 0, len(text)) # Apply only XML rules
                return # Skip other rules

        # --- Process Current Block ---
        self.setCurrentBlockState(self.NORMAL_STATE) # Assume normal unless changed below
        search_index = start_index

        while search_index < len(text):
            # Check for start of instructions block
            instr_start_match = self.instruction_start_expression.match(text, search_index)
            # Check for start of multi-line docstrings
            multi_double_match = self.tri_double_start_expression.match(text, search_index)
            multi_single_match = self.tri_single_start_expression.match(text, search_index)

            instr_start_pos = instr_start_match.capturedStart() if instr_start_match.hasMatch() else -1
            multi_double_start_pos = multi_double_match.capturedStart() if multi_double_match.hasMatch() else -1
            multi_single_start_pos = multi_single_match.capturedStart() if multi_single_match.hasMatch() else -1

            # Find the earliest delimiter
            first_delimiter_pos = -1
            delimiter_type = self.NORMAL_STATE

            if instr_start_pos != -1:
                first_delimiter_pos = instr_start_pos
                delimiter_type = self.IN_INSTRUCTIONS

            if multi_double_start_pos != -1 and (first_delimiter_pos == -1 or multi_double_start_pos < first_delimiter_pos):
                first_delimiter_pos = multi_double_start_pos
                delimiter_type = self.IN_TRIPLE_DOUBLE_DOCSTRING

            if multi_single_start_pos != -1 and (first_delimiter_pos == -1 or multi_single_start_pos < first_delimiter_pos):
                first_delimiter_pos = multi_single_start_pos
                delimiter_type = self.IN_TRIPLE_SINGLE_DOCSTRING

            # --- Apply Normal Highlighting Before Delimiter ---
            if first_delimiter_pos != -1:
                # Highlight the segment before the delimiter starts
                self.apply_python_xml_rules(text, search_index, first_delimiter_pos - search_index)
            else:
                # No more delimiters, highlight the rest of the line
                self.apply_python_xml_rules(text, search_index, len(text) - search_index)
                break # Finished processing this block

            # --- Process the Delimiter and Following Segment ---
            if delimiter_type == self.IN_INSTRUCTIONS:
                length = instr_start_match.capturedLength()
                self.highlight_xml_tag(text, first_delimiter_pos, length) # Highlight opening tag
                # Check if it also ends on this line
                instr_end_match = self.instruction_end_expression.match(text, first_delimiter_pos + length)
                if instr_end_match.hasMatch():
                    # Ends on the same line
                    end_len = instr_end_match.capturedLength()
                    self.highlight_xml_tag(text, instr_end_match.capturedStart(), end_len) # Highlight closing tag
                    self.setCurrentBlockState(self.NORMAL_STATE)
                    search_index = instr_end_match.capturedStart() + end_len
                else:
                    # Continues to next line
                    self.setCurrentBlockState(self.IN_INSTRUCTIONS)
                    # Highlight remaining part with only XML rules
                    self.highlight_xml_details(text, first_delimiter_pos + length, len(text) - (first_delimiter_pos + length))
                    search_index = len(text) # Stop processing this line

            elif delimiter_type == self.IN_TRIPLE_DOUBLE_DOCSTRING:
                search_index = self.highlight_multiline(text, self.tri_double_end_expression, self.IN_TRIPLE_DOUBLE_DOCSTRING, first_delimiter_pos, self.docstring_format)
                if search_index == -1: search_index = len(text) # Stop if continues

            elif delimiter_type == self.IN_TRIPLE_SINGLE_DOCSTRING:
                search_index = self.highlight_multiline(text, self.tri_single_end_expression, self.IN_TRIPLE_SINGLE_DOCSTRING, first_delimiter_pos, self.docstring_format)
                if search_index == -1: search_index = len(text) # Stop if continues


    def apply_python_xml_rules(self, text, start, length):
        """Applies Python and detailed XML highlighting rules to a segment."""
        if length <= 0:
            return

        segment = text[start : start + length]

        # Apply general Python rules first
        for pattern, fmt in self.python_highlighting_rules:
            match_iterator = pattern.globalMatch(segment)
            while match_iterator.hasNext():
                match = match_iterator.next()
                match_start = match.capturedStart()
                match_length = match.capturedLength()

                # Adjust offsets relative to the original text block
                original_start = start + match_start

                # Special handling for class/def names
                if pattern.pattern() == r'\b(class|def)\s+([a-zA-Z_][a-zA-Z0-9_]*)':
                    if match.lastCapturedIndex() >= 2:
                        self.setFormat(start + match.capturedStart(2), match.capturedLength(2), fmt)
                # Special handling for magic methods
                elif pattern.pattern() == r'\b(__\w+__)\b':
                     if match.lastCapturedIndex() >= 1:
                        self.setFormat(start + match.capturedStart(1), match.capturedLength(1), fmt)
                else:
                    self.setFormat(original_start, match_length, fmt)

        # Apply detailed XML rules (these might override some general rules like strings for attr values)
        self.highlight_xml_details(text, start, length)


    def highlight_xml_details(self, text, start, length):
         """Applies specific formatting to XML tag components."""
         if length <= 0:
             return
         segment = text[start : start + length]

         # Highlight delimiters first
         for delim_pattern in [r"</?", r"/?>"]:
             match_iterator = QRegularExpression(delim_pattern).globalMatch(segment)
             while match_iterator.hasNext():
                 match = match_iterator.next()
                 self.setFormat(start + match.capturedStart(), match.capturedLength(), self.xml_tag_delim_format)

         # Highlight tag names
         match_iterator = QRegularExpression(r"(?<=</?)\s*([\w\-\:]+)").globalMatch(segment)
         while match_iterator.hasNext():
             match = match_iterator.next()
             if match.lastCapturedIndex() >= 1:
                 self.setFormat(start + match.capturedStart(1), match.capturedLength(1), self.xml_tag_name_format)

         # Highlight attribute names
         match_iterator = QRegularExpression(r"\b([\w\-\:]+)\s*(?==)").globalMatch(segment)
         while match_iterator.hasNext():
             match = match_iterator.next()
             if match.lastCapturedIndex() >= 1:
                 self.setFormat(start + match.capturedStart(1), match.capturedLength(1), self.xml_attr_name_format)

         # Highlight attribute values (strings)
         for quote_char in ["'", '"']:
             pattern = quote_char + r"[^" + quote_char + r"\\]*(\\.[^" + quote_char + r"\\]*)*" + quote_char
             match_iterator = QRegularExpression(pattern).globalMatch(segment)
             while match_iterator.hasNext():
                 match = match_iterator.next()
                 # Apply value format, potentially overriding general string format if needed
                 self.setFormat(start + match.capturedStart(), match.capturedLength(), self.xml_attr_value_format)


    def highlight_xml_tag(self, text, start, length):
        """Highlights an entire XML tag with detailed formatting."""
        # Use the detailed highlighter for consistency
        self.highlight_xml_details(text, start, length)


    def highlight_multiline(self, text, end_expression, state, start_index, fmt):
        """Helper to highlight multi-line constructs (docstrings) and manage block state."""
        match = end_expression.match(text, start_index)
        end_index = match.capturedStart() if match.hasMatch() else -1
        delimiter_length = end_expression.pattern().length() # Length of """ or '''

        if end_index == -1:
            # String/Docstring continues to the next block
            self.setCurrentBlockState(state)
            length = len(text) - start_index
            self.setFormat(start_index, length, fmt) # Apply the specific format (docstring)
            return -1 # Indicate highlighting finished for this block
        else:
            # String/Docstring ends in this block
            length = end_index - start_index + delimiter_length
            self.setFormat(start_index, length, fmt) # Apply the specific format
            # Return the index *after* the closing delimiter
            return start_index + length