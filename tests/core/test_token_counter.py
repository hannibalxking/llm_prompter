# tests/test_token_counter.py
import pytest
# Fixes critical issue #1 & #3: Use alias, use range assertions
from promptbuilder.core.token_counter import count_tokens, TIKTOKEN_AVAILABLE, DEFAULT_ENCODING

# Skip all tests in this module if tiktoken is not available
pytestmark = pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken library not installed or failed to load")

def test_count_tokens_simple():
    text = "hello world"
    # Assuming cl100k_base encoding
    expected_tokens = 2
    assert count_tokens(text, DEFAULT_ENCODING) == expected_tokens

def test_count_tokens_empty():
     assert count_tokens("") == 0

def test_count_tokens_longer_text():
    text = "This is a slightly longer sentence to test token counting."
    # Don't assert exact count, check a reasonable range
    token_count = count_tokens(text, DEFAULT_ENCODING)
    assert 5 < token_count < 20 # Example range for cl100k_base

def test_count_tokens_special_chars_and_xml():
    text = "<instructions>\n  <objective>Test</objective>\n</instructions>"
    # Token count varies with tokenizer versions. Use a range.
    token_count = count_tokens(text, DEFAULT_ENCODING)
    # Example range for cl100k_base - adjust if needed after checking manually
    assert 5 < token_count < 15

def test_count_tokens_different_encoding():
    text = "hello world"
    # gpt2 tokenizer usually gives different counts
    gpt2_count = count_tokens(text, encoding_name="gpt2")
    cl100k_count = count_tokens(text, encoding_name="cl100k_base")
    # Basic check that they might differ, or check a range for gpt2
    assert gpt2_count >= 0
    assert cl100k_count >= 0
    # Example range check for gpt2
    assert 1 < gpt2_count < 5

def test_count_tokens_estimation_fallback(mocker):
    # Test the estimation fallback if tiktoken fails (requires mocking)
    # Temporarily make the library seem unavailable or mock the encode call
    mocker.patch('promptbuilder.core.token_counter.TIKTOKEN_AVAILABLE', False)
    # Or mock the _get_cached_encoder to return None
    # mocker.patch('promptbuilder.core.token_counter._get_cached_encoder', return_value=None)

    text = "This text will be estimated based on characters."
    expected_estimation = len(text) // 4
    assert count_tokens(text) == expected_estimation

    # Test estimation for empty string with fallback
    assert count_tokens("") == 0