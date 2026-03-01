"""Tests for the committer module."""

import sys
from datetime import date
from unittest.mock import MagicMock, patch

from memory import Memory
from committer import apply_user_urls, build_ai_request, extract_urls, replace_urls_with_placeholders


def test_build_ai_request():
    memories = [
        Memory(target=date(2026, 3, 1), expires=date(2026, 4, 1),
               content="Planning", title="Standup", time="10:00", place="Room A"),
    ]
    prompt = build_ai_request("Team meeting next Thursday", memories, date(2026, 2, 18))

    assert "2026-02-18" in prompt
    assert "Team meeting next Thursday" in prompt
    assert "Standup" in prompt
    assert "10:00" in prompt
    assert "Room A" in prompt
    assert "slug" in prompt.lower()


def test_build_ai_request_ongoing_memory():
    memories = [
        Memory(target=None, expires=date(2026, 2, 22),
               content="Every week", title="Sunday Worship"),
    ]
    prompt = build_ai_request("What's happening?", memories, date(2026, 2, 18))
    assert "target=ongoing" in prompt
    assert "Sunday Worship" in prompt


def test_build_ai_request_no_memories():
    prompt = build_ai_request("New event Friday", [], date(2026, 2, 18))

    assert "(none)" in prompt
    assert "New event Friday" in prompt


def test_call_ai():
    mock_response = MagicMock()
    mock_response.text = '{"action": "create", "target": "2026-03-01", "expires": "2026-03-31", "title": "Meeting", "time": null, "place": null, "content": "Team sync"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        result = call_ai("test prompt")

    assert result["action"] == "create"
    assert result["title"] == "Meeting"
    mock_genai.Client.assert_called_once_with(api_key="test-key")


def test_build_ai_request_with_attachments():
    prompt = build_ai_request(
        "Meeting with flyer", [], date(2026, 2, 18),
        attachment_urls=["https://storage.googleapis.com/bucket/flyer.pdf"],
    )
    assert "https://storage.googleapis.com/bucket/flyer.pdf" in prompt
    assert "Attached file URLs" in prompt


def test_build_ai_request_no_attachments():
    prompt = build_ai_request("Meeting", [], date(2026, 2, 18))
    assert "Attached file URLs" not in prompt


# --- URL preference tests ---


def test_extract_urls():
    text = "Check https://example.com/a and http://example.org/b please"
    assert extract_urls(text) == ["https://example.com/a", "http://example.org/b"]


def test_extract_urls_none():
    assert extract_urls("No links here") == []


def test_apply_user_urls_replaces_ai_link_in_title():
    title = "[Meeting](https://ai-generated.com/link)"
    content = "Some description"
    user_urls = ["https://user-provided.com/real"]
    new_title, new_content = apply_user_urls(title, content, user_urls)
    assert new_title == "[Meeting](https://user-provided.com/real)"
    assert "https://user-provided.com/real" in new_content


def test_apply_user_urls_wraps_plain_title():
    title = "Meeting"
    content = "Some description"
    user_urls = ["https://user-provided.com/real"]
    new_title, new_content = apply_user_urls(title, content, user_urls)
    assert new_title == "[Meeting](https://user-provided.com/real)"


def test_apply_user_urls_appends_missing_to_content():
    title = "Meeting"
    content = "Already has https://a.com here"
    user_urls = ["https://a.com", "https://b.com"]
    new_title, new_content = apply_user_urls(title, content, user_urls)
    # a.com already present, b.com should be appended
    assert "https://b.com" in new_content
    assert "Links:" in new_content
    # a.com should NOT be in the appended section (it was already present)
    links_section = new_content.split("Links:")[1]
    assert "https://a.com" not in links_section


def test_apply_user_urls_no_urls_is_noop():
    title, content = apply_user_urls("Title", "Content", [])
    assert title == "Title"
    assert content == "Content"


# --- Unicode / complex URL tests (issue #74) ---

UNICODE_URL = (
    "https://www.stemofjesse.org/doku/doku.php/"
    "%E6%99%A8%E5%85%B4%E5%9C%A3%E8%A8%80:2025:2025.05."
    "%E7%A7%8B%E5%AD%A3%E9%95%BF%E8%80%81%E8%B4%9F%E8%B4%A3"
    "%E5%BC%9F%E5%85%84%E8%AE%AD%E7%BB%83:%E7%AC%AC%E5%85%AD%E5%91%A8"
)

ISSUE_74_MESSAGE = f"本周晨兴链接 {UNICODE_URL}"


def test_extract_urls_unicode_percent_encoded():
    """URLs with percent-encoded Chinese characters and colons are extracted."""
    urls = extract_urls(ISSUE_74_MESSAGE)
    assert urls == [UNICODE_URL]


def test_extract_urls_raw_unicode():
    """URLs with raw (non-encoded) Chinese characters and colons are extracted."""
    raw_url = "https://www.stemofjesse.org/doku/doku.php/晨兴圣言:2025:第六周"
    urls = extract_urls(f"链接 {raw_url}")
    assert urls == [raw_url]


def test_apply_user_urls_unicode_url():
    """apply_user_urls wraps title with a unicode URL correctly."""
    title = "本周晨兴"
    content = "晨兴圣言链接"
    new_title, new_content = apply_user_urls(title, content, [UNICODE_URL])
    assert new_title == f"[本周晨兴]({UNICODE_URL})"
    assert UNICODE_URL in new_content


def test_replace_urls_with_placeholders_basic():
    text = "Check https://example.com/page for details"
    sanitised, urls = replace_urls_with_placeholders(text)
    assert sanitised == "Check [link1] for details"
    assert urls == ["https://example.com/page"]


def test_replace_urls_with_placeholders_multiple():
    text = "See https://a.com and https://b.com/path"
    sanitised, urls = replace_urls_with_placeholders(text)
    assert sanitised == "See [link1] and [link2]"
    assert urls == ["https://a.com", "https://b.com/path"]


def test_replace_urls_with_placeholders_no_urls():
    text = "No links here"
    sanitised, urls = replace_urls_with_placeholders(text)
    assert sanitised == "No links here"
    assert urls == []


def test_replace_urls_with_placeholders_unicode_url():
    """Complex percent-encoded URLs are replaced with simple placeholders."""
    sanitised, urls = replace_urls_with_placeholders(ISSUE_74_MESSAGE)
    assert "[link1]" in sanitised
    assert UNICODE_URL not in sanitised
    assert "本周晨兴链接" in sanitised
    assert urls == [UNICODE_URL]


def test_call_ai_retries_on_empty_response():
    """call_ai retries when Gemini returns an empty response."""
    mock_response_empty = MagicMock()
    mock_response_empty.text = None

    mock_response_ok = MagicMock()
    mock_response_ok.text = '{"action": "create", "content": "test", "target": null, "expires": null, "title": "T"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [mock_response_empty, mock_response_ok]

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        result = call_ai("test prompt")

    assert result["action"] == "create"
    assert mock_client.models.generate_content.call_count == 2


def test_call_ai_retries_on_invalid_json():
    """call_ai retries when Gemini returns invalid JSON."""
    mock_response_bad = MagicMock()
    mock_response_bad.text = "not valid json {"

    mock_response_ok = MagicMock()
    mock_response_ok.text = '{"action": "create", "content": "ok", "title": "T"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [mock_response_bad, mock_response_ok]

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        result = call_ai("test prompt")

    assert result["action"] == "create"
    assert mock_client.models.generate_content.call_count == 2


def test_call_ai_retries_on_missing_keys():
    """call_ai retries when response JSON is missing required keys."""
    mock_response_bad = MagicMock()
    mock_response_bad.text = '{"title": "no action or content"}'

    mock_response_ok = MagicMock()
    mock_response_ok.text = '{"action": "create", "content": "ok", "title": "T"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [mock_response_bad, mock_response_ok]

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        result = call_ai("test prompt")

    assert result["action"] == "create"
    assert mock_client.models.generate_content.call_count == 2


def test_call_ai_raises_after_all_retries_exhausted():
    """call_ai raises after all retry attempts fail."""
    mock_response_empty = MagicMock()
    mock_response_empty.text = None

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response_empty

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    import pytest
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        with pytest.raises(ValueError, match="empty response"):
            call_ai("test prompt")
