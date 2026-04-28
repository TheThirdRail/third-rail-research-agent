from src.api.routes import reports


def test_pdf_styles_remove_heading_orphan_rules_and_reduce_font_size():
    html = reports.build_report_html("## 4. Agreed Facts\n\nA fact line")

    assert "break-after: avoid-page" not in html
    assert "page-break-after: avoid" not in html
    assert "break-inside: avoid-page" not in html
    assert "page-break-inside: avoid" not in html
    assert "break-before: avoid-page" not in html
    assert "page-break-before: avoid" not in html
    assert "font-size: 11.5px;" in html
    assert "font-size: 10.5px;" in html
