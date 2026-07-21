"""
프로그램명: 창의적 개인 실습 보고서 PDF 변환기
작성자: 임해안
작성일: 2026-07-21

목적:
    - REPORT.md와 캡처 이미지를 인쇄용 HTML로 변환한다.
    - Google Chrome Headless를 이용해 A4 PDF 보고서를 생성한다.
"""

import subprocess
import tempfile
from pathlib import Path

import markdown


REPORT_DIR = Path(__file__).resolve().parent
MARKDOWN_PATH = REPORT_DIR / "REPORT.md"
HTML_PATH = REPORT_DIR / "REPORT.html"
PDF_PATH = REPORT_DIR / "Advanced_창의적실습_보고서.pdf"
CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


PRINT_STYLE = """
@page {
  size: A4;
  margin: 15mm 14mm 16mm;
}

* {
  box-sizing: border-box;
}

html {
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

body {
  margin: 0 auto;
  color: #172033;
  font-family: "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  font-size: 10.2pt;
  line-height: 1.58;
  word-break: keep-all;
  overflow-wrap: break-word;
}

h1 {
  margin: 0 0 22px;
  padding: 30px 10px 24px;
  border-bottom: 3px solid #1f4b99;
  color: #183153;
  font-size: 24pt;
  line-height: 1.3;
  text-align: center;
}

h2 {
  margin: 28px 0 12px;
  padding: 7px 10px;
  border-left: 5px solid #2563eb;
  background: #eef4ff;
  color: #183153;
  font-size: 16pt;
  break-after: avoid-page;
}

h3 {
  margin: 22px 0 8px;
  color: #1f4b99;
  font-size: 12.5pt;
  break-after: avoid-page;
}

p {
  margin: 7px 0;
}

ul, ol {
  margin: 7px 0;
  padding-left: 23px;
}

li {
  margin: 3px 0;
}

blockquote {
  margin: 14px 0;
  padding: 10px 14px;
  border-left: 4px solid #2563eb;
  background: #f1f6ff;
  color: #244064;
  font-weight: 600;
}

table {
  width: 100%;
  margin: 12px 0 16px;
  border-collapse: collapse;
  font-size: 8.8pt;
  break-inside: avoid-page;
}

th, td {
  padding: 6px 7px;
  border: 1px solid #cdd7e5;
  text-align: left;
  vertical-align: top;
}

th {
  background: #eaf1fb;
  color: #183153;
  font-weight: 700;
}

code {
  padding: 1px 4px;
  border-radius: 3px;
  background: #eef2f7;
  color: #b42318;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: .9em;
}

pre {
  margin: 11px 0;
  padding: 12px 14px;
  border-radius: 6px;
  background: #172033;
  color: #f8fafc;
  white-space: pre-wrap;
  break-inside: avoid-page;
}

pre code {
  padding: 0;
  background: transparent;
  color: inherit;
}

img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 190mm;
  margin: 12px auto 16px;
  border: 1px solid #d7deea;
  object-fit: contain;
  break-inside: avoid-page;
}

strong {
  color: #183153;
}

hr {
  height: 0;
  margin: 18px 0;
  border: 0;
  border-top: 1px solid #d7deea;
}
"""


def build_html() -> Path:
    """Markdown 본문을 표·코드 확장과 인쇄 스타일이 적용된 HTML로 변환한다."""
    source = MARKDOWN_PATH.read_text(encoding="utf-8")
    body = markdown.markdown(
        source,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html = f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>창의적 개인 실습 보고서</title>
    <style>{PRINT_STYLE}</style>
  </head>
  <body>{body}</body>
</html>
"""
    HTML_PATH.write_text(html, encoding="utf-8")
    return HTML_PATH


def build_pdf(html_path: Path) -> Path:
    """Chrome Headless 인쇄 기능으로 HTML을 A4 PDF로 변환한다."""
    if not CHROME_PATH.is_file():
        raise FileNotFoundError(f"Google Chrome 실행 파일이 없습니다: {CHROME_PATH}")

    with tempfile.TemporaryDirectory(prefix="advanced-report-chrome-") as profile_dir:
        subprocess.run(
            [
                str(CHROME_PATH),
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile_dir}",
                f"--print-to-pdf={PDF_PATH}",
                html_path.as_uri(),
            ],
            check=True,
        )

    if not PDF_PATH.is_file() or PDF_PATH.stat().st_size == 0:
        raise OSError("PDF 보고서가 생성되지 않았습니다.")
    return PDF_PATH


def main() -> None:
    """REPORT.md를 HTML과 PDF로 변환하고 결과 경로를 출력한다."""
    html_path = build_html()
    pdf_path = build_pdf(html_path)
    print(f"HTML 생성 완료: {html_path}")
    print(f"PDF 생성 완료: {pdf_path}")
    print(f"PDF 파일 크기: {pdf_path.stat().st_size / 1024:,.1f} KB")


if __name__ == "__main__":
    main()
