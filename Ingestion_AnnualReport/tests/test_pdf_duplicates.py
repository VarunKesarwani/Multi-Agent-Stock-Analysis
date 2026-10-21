"""Conversion/resume behavior without requiring PDF engines or model services."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture
def converter(monkeypatch, tmp_path):
    # Isolate optional PDF engines; exercise the real conversion and cache code.
    primary = Mock(return_value="# Annual report\nRevenue increased.")
    fallback = Mock(return_value=SimpleNamespace(text_content="Fallback report"))
    monkeypatch.setitem(sys.modules, "pymupdf4llm", SimpleNamespace(to_markdown=primary))
    monkeypatch.setitem(sys.modules, "markitdown", SimpleNamespace(
        MarkItDown=lambda: SimpleNamespace(convert=fallback)))
    monkeypatch.setitem(sys.modules, "pandas", SimpleNamespace())
    settings = SimpleNamespace(annual_pdf_dir=tmp_path, symbols_csv=tmp_path / "symbols.csv",
                               markdown_dir=tmp_path / "md", summary_csv=tmp_path / "summary.csv")
    monkeypatch.setitem(sys.modules, "ingestion_settings", SimpleNamespace(
        DocumentSettings=SimpleNamespace(from_env=lambda: settings)))
    spec = importlib.util.spec_from_file_location(
        "pdf_process_under_test", Path(__file__).resolve().parents[1] / "pdf_process.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, primary, fallback


def run(converter, tmp_path, name="annual.pdf", content=b"original PDF", **kwargs):
    module, _, _ = converter
    pdf = tmp_path / name
    pdf.write_bytes(content)
    return module.read_pdf_file(str(pdf), "TCS", "2025", str(tmp_path / "md"), **kwargs)


def test_repeat_and_renamed_copy_skip(converter, tmp_path):
    first = run(converter, tmp_path)
    assert first["status"] == "success"
    assert run(converter, tmp_path)["skip_reason"] == "duplicate_pdf"
    renamed = run(converter, tmp_path, "annual_copy.pdf")
    assert renamed["status"] == "skipped"
    assert renamed["output_file"] == first["output_file"]
    assert converter[1].call_count == 1
    assert len(list((tmp_path / "md").glob("*.md"))) == 1


def test_changed_content_and_force_reprocess(converter, tmp_path):
    run(converter, tmp_path)
    assert run(converter, tmp_path, content=b"updated PDF")["status"] == "success"
    assert run(converter, tmp_path, content=b"updated PDF", force=True)["status"] == "success"
    assert converter[1].call_count == 3


@pytest.mark.parametrize("damage", ["missing", "empty", "truncated", "record"])
def test_invalid_output_or_record_retries(converter, tmp_path, damage):
    first = run(converter, tmp_path)
    output = tmp_path / "md" / first["output_file"]
    if damage == "missing":
        output.unlink()
    elif damage == "record":
        next((tmp_path / "md" / ".pdf_conversion_cache").glob("*.json")).write_text("broken")
    else:
        output.write_text("" if damage == "empty" else "incomplete markdown")
    assert run(converter, tmp_path)["status"] == "success"
    assert converter[1].call_count == 2


def test_failed_parse_retries_and_fallback_is_cached(converter, tmp_path):
    _, primary, fallback = converter
    primary.side_effect = RuntimeError("primary failed")
    fallback.side_effect = RuntimeError("fallback failed")
    assert run(converter, tmp_path)["status"] == "failed"
    assert not list((tmp_path / "md").rglob("*.json"))
    fallback.side_effect = None
    assert run(converter, tmp_path)["parsed_by"] == "markitdown"
    assert run(converter, tmp_path)["status"] == "skipped"
    assert primary.call_count == 2


def test_empty_parse_not_cached(converter, tmp_path):
    converter[1].return_value = " "
    assert run(converter, tmp_path)["status"] == "failed"
    converter[1].return_value = "Valid report"
    assert run(converter, tmp_path)["status"] == "success"


def test_context_is_not_deduplicated(converter, tmp_path):
    run(converter, tmp_path)
    module = converter[0]
    pdf = str(tmp_path / "annual.pdf")
    output = str(tmp_path / "md")
    assert module.read_pdf_file(pdf, "INFY", "2025", output)["status"] == "success"
    assert module.read_pdf_file(pdf, "TCS", "2024", output)["status"] == "success"
    assert run(converter, tmp_path, "quarterly.pdf")["status"] == "success"
    assert converter[1].call_count == 4


def test_threaded_duplicates_parse_once(converter, tmp_path):
    module, primary, _ = converter
    files = [tmp_path / "annual.pdf", tmp_path / "annual_copy.pdf"]
    for pdf in files:
        pdf.write_bytes(b"same content")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda pdf: module.read_pdf_file(
            str(pdf), "TCS", "2025", str(tmp_path / "md")), files))
    assert sorted(r["status"] for r in results) == ["skipped", "success"]
    assert primary.call_count == 1


def test_legacy_output_converted_once(converter, tmp_path):
    module = converter[0]
    pdf = tmp_path / "annual.pdf"
    pdf.write_bytes(b"original PDF")
    output = tmp_path / "md"
    output.mkdir()
    (output / module.markdown_filename(str(pdf), "TCS", "2025")).write_text("old output")
    assert run(converter, tmp_path)["status"] == "success"
    assert run(converter, tmp_path)["status"] == "skipped"


def test_failed_write_leaves_no_completion_record(converter, tmp_path, monkeypatch):
    monkeypatch.setattr(converter[0], "atomic_write", Mock(side_effect=OSError("disk full")))
    assert run(converter, tmp_path)["status"] == "failed"
    assert not list((tmp_path / "md").rglob("*.json"))
