"""Report export API routes."""

import logging

import bleach
from fastapi import APIRouter, HTTPException, Response
from markdown import markdown as markdown_to_html
from pydantic import BaseModel, Field

from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

PDF_FORMAT = "Letter"
PDF_MARGIN_MM = {"top": 20, "right": 20, "bottom": 20, "left": 20}
REPORT_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline';"
ALLOWED_REPORT_TAGS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
ALLOWED_REPORT_ATTRIBUTES = {
    "a": ["href", "title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
ALLOWED_REPORT_PROTOCOLS = frozenset({"http", "https", "mailto"})


class ReportPdfRequest(BaseModel):
    """Request payload for report PDF export."""

    report_markdown: str = Field(..., description="Markdown report content")


NEON_STYLES = """
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 32px;
    background: #0d0221;
    color: #e6e6e6;
    font-family: "Fira Code", "Courier New", monospace;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  h1, h2, h3 {
    color: #00f3ff;
    font-family: "Fira Code", "Courier New", monospace;
  }
  h2 { color: #bd00ff; }
  a { color: #00f3ff; text-decoration: none; }
  a:hover { color: #ffffff; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    background: rgba(5, 0, 20, 0.6);
    color: #f1f1f1;
  }
  th, td {
    border: 1px solid rgba(0, 243, 255, 0.35);
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
    font-size: 11.5px;
  }
  th {
    background: rgba(0, 243, 255, 0.1);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 10.5px;
  }
  tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.04);
  }
  code {
    background: rgba(255, 255, 255, 0.08);
    padding: 2px 4px;
    border-radius: 3px;
  }
  @page { margin: 20mm; }
  @media print {
    body { padding: 24px; }
  }
</style>
"""


def build_report_html(markdown: str) -> str:
    """Convert markdown report content into styled HTML."""
    raw_body = markdown_to_html(
        markdown,
        extensions=["tables", "footnotes", "fenced_code"],
        output_format="html5",
    )
    body = bleach.clean(
        raw_body,
        tags=ALLOWED_REPORT_TAGS,
        attributes=ALLOWED_REPORT_ATTRIBUTES,
        protocols=ALLOWED_REPORT_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="{REPORT_CSP}" />
    <title>Research Report</title>
    {NEON_STYLES}
  </head>
  <body>
    {body}
  </body>
</html>
"""


async def render_report_pdf(markdown: str) -> bytes:
    """Render markdown into a PDF using Playwright."""
    from playwright.async_api import async_playwright

    html = build_report_html(markdown)
    async with async_playwright() as playwright:
        browser = None
        context = None
        page = None
        try:
            browser = await playwright.chromium.launch(args=["--no-sandbox"])
            context = await browser.new_context(java_script_enabled=False)

            async def _abort_route(route):
                await route.abort()

            await context.route("**/*", _abort_route)
            page = await context.new_page()
            await page.set_content(html, wait_until="load")
            pdf_bytes = await page.pdf(
                format=PDF_FORMAT,
                print_background=True,
                margin={
                    "top": f"{PDF_MARGIN_MM['top']}mm",
                    "right": f"{PDF_MARGIN_MM['right']}mm",
                    "bottom": f"{PDF_MARGIN_MM['bottom']}mm",
                    "left": f"{PDF_MARGIN_MM['left']}mm",
                },
            )
        finally:
            if page is not None:
                await page.close()
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
    return pdf_bytes


@router.post("/reports/pdf")
async def create_report_pdf(request: ReportPdfRequest) -> Response:
    """Generate a PDF report from markdown."""
    if not request.report_markdown.strip():
        raise HTTPException(status_code=400, detail="report_markdown is required")
    if len(request.report_markdown) > settings.max_report_markdown_chars:
        raise HTTPException(status_code=413, detail="report_markdown is too large")
    try:
        pdf_bytes = await render_report_pdf(request.report_markdown)
    except Exception as exc:
        logger.exception("PDF export failed")
        raise HTTPException(
            status_code=500,
            detail="PDF export failed. Check server logs for details.",
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=research-report.pdf"},
    )
