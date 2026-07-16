from backend.services.content_safety.normalization import normalize_for_scan


def test_scan_copy_normalizes_unicode_and_removes_invisible_controls():
    result = normalize_for_scan("ＡＰＩ\u200b KEY\u202e = secret")

    assert result == "api key = secret"


def test_scan_copy_decodes_html_entities_once_and_collapses_whitespace():
    result = normalize_for_scan("&lt;SCRIPT&gt;\r\n\talert(1)&lt;/SCRIPT&gt;")

    assert result == "<script> alert(1)</script>"


def test_scan_copy_does_not_double_decode_entities():
    result = normalize_for_scan("&amp;lt;script&amp;gt;")

    assert result == "&lt;script&gt;"
