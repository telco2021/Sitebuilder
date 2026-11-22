from liquid.design import parse_design, render_design


def test_design_keeps_layout_and_drops_scripts():
    document = parse_design(
        """
        <h1 onclick="alert(1)">Headline</h1>
        <section class="hero" style="color:red;background:url(javascript:alert(1))">
          <a href="javascript:alert(1)">Bad</a>
          <a href="/s/gateway/software-development">Good</a>
          <img src="/media/3" alt="A room">
          <img src="https://evil.example/a.png" alt="nope">
        </section>
        <script>alert(1)</script>
        """,
        "h2{color:#112233}.hero{padding:12px}body{background:url(https://evil.example/a.png)}@import url(https://evil.example/a.css);",
        {3},
    )
    html = render_design(document)
    assert "<script" not in html.lower()
    assert "javascript" not in html.lower()
    assert "onclick" not in html.lower()
    assert "evil.example" not in html
    assert "<h2" in html
    assert "<h1" not in html
    assert 'href="/s/gateway/software-development"' in html
    assert 'src="/media/3"' in html
    assert "https://evil.example/a.png" not in html
    assert ".hero{padding:12px}" in html
    assert "@import" not in html
    assert "expression" not in html


def test_design_rejects_a_page_that_is_too_large():
    from liquid.textutil import FormError
    import pytest

    with pytest.raises(FormError):
        parse_design("a" * 150_001, "", set())
