from pathlib import Path

from openpyxl import Workbook

from backend.ingestion import extract_text


def test_extract_txt(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    assert extract_text(f) == "hello world"


def test_extract_csv(tmp_path: Path):
    f = tmp_path / "a.csv"
    f.write_text("name,age\nIvan,30\nAnna,25\n", encoding="utf-8")
    text = extract_text(f)
    assert "name: Ivan; age: 30" in text
    assert "name: Anna; age: 25" in text


def test_extract_html(tmp_path: Path):
    f = tmp_path / "a.html"
    f.write_text(
        "<html><head><script>bad()</script></head>"
        "<body><h1>Title</h1><p>Body text</p></body></html>",
        encoding="utf-8",
    )
    text = extract_text(f)
    assert "Title" in text
    assert "Body text" in text
    assert "bad()" not in text


def test_extract_xlsx(tmp_path: Path):
    f = tmp_path / "a.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "People"
    ws.append(["Name", "Salary"])
    ws.append(["Ivan", 100])
    wb.save(f)
    text = extract_text(f)
    assert "Sheet: People" in text
    assert "Name: Ivan; Salary: 100" in text


def test_extract_markdown_as_plain_text(tmp_path: Path):
    f = tmp_path / "a.md"
    f.write_text("# Header\n\nSome **bold** text", encoding="utf-8")
    text = extract_text(f)
    assert "Header" in text
    assert "bold" in text
