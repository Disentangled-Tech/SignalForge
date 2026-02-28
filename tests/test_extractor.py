"""Tests for the HTML text extractor service."""

from __future__ import annotations

from app.services.extractor import MAX_TEXT_LENGTH, extract_text


class TestExtractTextBasic:
    def test_extracts_paragraph_text(self):
        html = "<html><body><p>Hello world</p></body></html>"
        assert extract_text(html) == "Hello world"

    def test_preserves_multiple_paragraphs(self):
        html = "<html><body><p>First</p><p>Second</p></body></html>"
        result = extract_text(html)
        assert "First" in result
        assert "Second" in result

    def test_strips_html_tags(self):
        html = "<p>Some <b>bold</b> and <i>italic</i> text</p>"
        result = extract_text(html)
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold" in result
        assert "italic" in result


class TestExtractTextTagRemoval:
    def test_removes_script_tags(self):
        html = "<body><script>alert('x')</script><p>Content</p></body>"
        result = extract_text(html)
        assert "alert" not in result
        assert "Content" in result

    def test_removes_style_tags(self):
        html = "<body><style>.a{color:red}</style><p>Visible</p></body>"
        result = extract_text(html)
        assert "color" not in result
        assert "Visible" in result

    def test_removes_nav_tags(self):
        html = "<body><nav>Menu Item</nav><main>Main content</main></body>"
        result = extract_text(html)
        assert "Menu Item" not in result
        assert "Main content" in result

    def test_removes_footer_tags(self):
        html = "<body><p>Body</p><footer>Footer info</footer></body>"
        result = extract_text(html)
        assert "Footer info" not in result
        assert "Body" in result

    def test_removes_header_tags(self):
        html = "<body><header>Site Header</header><p>Content</p></body>"
        result = extract_text(html)
        assert "Site Header" not in result
        assert "Content" in result

    def test_removes_aside_tags(self):
        html = "<body><aside>Sidebar</aside><article>Article text</article></body>"
        result = extract_text(html)
        assert "Sidebar" not in result
        assert "Article text" in result


class TestExtractTextWhitespace:
    def test_collapses_multiple_spaces(self):
        html = "<p>Hello     world</p>"
        assert extract_text(html) == "Hello world"

    def test_collapses_newlines(self):
        html = "<p>Line one</p>\n\n\n<p>Line two</p>"
        result = extract_text(html)
        assert "\n" not in result
        assert "Line one" in result
        assert "Line two" in result

    def test_strips_leading_trailing_whitespace(self):
        html = "  <p>  Text  </p>  "
        result = extract_text(html)
        assert result == "Text"


class TestExtractTextCharLimit:
    def test_limits_output_to_max_length(self):
        # Create HTML with text exceeding the limit
        long_text = "A" * (MAX_TEXT_LENGTH + 1000)
        html = f"<p>{long_text}</p>"
        result = extract_text(html)
        assert len(result) <= MAX_TEXT_LENGTH

    def test_short_text_not_truncated(self):
        html = "<p>Short text</p>"
        result = extract_text(html)
        assert result == "Short text"


class TestExtractTextEmpty:
    def test_returns_empty_for_none(self):
        assert extract_text(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert extract_text("") == ""

    def test_returns_empty_for_whitespace_only_html(self):
        assert extract_text("   ") == ""

    def test_returns_empty_for_tags_only(self):
        html = "<script>alert('x')</script>"
        assert extract_text(html) == ""
