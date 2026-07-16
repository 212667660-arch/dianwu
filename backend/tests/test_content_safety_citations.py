from backend.services.content_safety.citations import validate_citations


def test_known_server_reference_is_allowed():
    result = validate_citations("一次函数定义[资料1]", allowed={"资料1", "资料2"})

    assert result.allowed is True
    assert result.used_references == ["资料1"]
    assert result.reason_codes == []


def test_unknown_reference_is_rejected_without_silent_deletion():
    body = "结论依赖未知材料[资料99]"
    result = validate_citations(body, allowed={"资料1"})

    assert result.allowed is False
    assert result.used_references == ["资料99"]
    assert result.reason_codes == ["CONTENT_CITATION_NOT_ALLOWED"]
    assert body.endswith("[资料99]")


def test_model_markdown_link_never_becomes_a_trusted_source():
    result = validate_citations("[点此](https://evil.example/x)", allowed={"资料1"})

    assert result.allowed is False
    assert "MODEL_LINK_NOT_ALLOWED" in result.reason_codes


def test_dangerous_and_raw_urls_are_not_allowed_in_generated_body():
    dangerous = validate_citations("javascript:alert(1)", allowed=set())
    raw = validate_citations("访问 https://example.test", allowed=set())

    assert dangerous.allowed is False
    assert raw.allowed is False
    assert "MODEL_URL_NOT_ALLOWED" in dangerous.reason_codes
    assert "MODEL_URL_NOT_ALLOWED" in raw.reason_codes
