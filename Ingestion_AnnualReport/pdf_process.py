import os
import glob
import argparse
import re
import time
import sys
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import pymupdf4llm
from markitdown import MarkItDown

from ingestion_settings import DocumentSettings
from pdf_conversion_cache import ConversionCache, atomic_write, file_sha256

_settings = DocumentSettings.from_env()
BASE_DIR = str(_settings.annual_pdf_dir)
CSV_FILE_PATH = str(_settings.symbols_csv)
OUTPUT_DIR = str(_settings.markdown_dir)
SUMMARY_CSV_PATH = str(_settings.summary_csv)


def log_msg(msg):
    """
    Prints immediately to stdout and flushes the buffer 
    to ensure real-time terminal output without buffering delays.
    """
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")
    sys.stdout.flush()


def classify_report_period(pdf_path):
    """Use explicit words in the source filename or directory; do not guess."""
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    parent = os.path.basename(os.path.dirname(pdf_path))
    labels = f"{name} {parent}".lower()
    if re.search(r"half[\s_-]*year(?:ly)?|semi[\s_-]*annual|(?<![a-z0-9])(?:h[12]|hy[12]?)(?![a-z0-9])", labels):
        return "HalfYearly"
    if re.search(r"quarter(?:ly)?|(?<![a-z0-9])q[1-4](?![a-z0-9])", labels):
        return "Quarterly"
    if re.search(r"annual|(?<![a-z0-9])ar(?![a-z0-9])", labels):
        return "Annual"
    return "Unknown"


def source_fingerprint(pdf_path):
    """Distinguish different PDFs even when their names normalize alike."""
    return file_sha256(pdf_path)[:12]


def markdown_filename(pdf_path, symbol, year, source_hash=None):
    period = classify_report_period(pdf_path)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")[:80] or "report"
    fingerprint = source_hash[:12] if source_hash else source_fingerprint(pdf_path)
    return f"{symbol}_{year}_{period}_{safe_stem}_{fingerprint}.md"


def read_pdf_file(pdf_path, symbol, year, output_dir, force=False):
    """Skip completed content before invoking either PDF parser."""
    started = time.time()
    try:
        source_hash = file_sha256(pdf_path)
        cache = ConversionCache(
            output_dir, source_hash, symbol, year, classify_report_period(pdf_path)
        )
        with cache.lock:
            existing = cache.completed() if not force else None
            if existing:
                log_msg(f"  [SKIP DUPLICATE] '{os.path.basename(pdf_path)}' -> {existing['output_file']}")
                return {
                    "symbol": symbol, "year": year,
                    "file_name": os.path.basename(pdf_path), "status": "skipped",
                    "parsed_by": existing.get("parsed_by", "none"),
                    "processing_time_sec": round(time.time() - started, 2),
                    "error_message": "", "skip_reason": "duplicate_pdf",
                    "output_file": existing["output_file"],
                }
            result = _convert_pdf_file(pdf_path, symbol, year, output_dir, source_hash)
            if result["status"] == "success":
                # A changing source must never acquire a completion record.
                if file_sha256(pdf_path) != source_hash:
                    raise ValueError("PDF changed during conversion; rerun this file")
                output_file = markdown_filename(pdf_path, symbol, year, source_hash)
                result["output_file"] = output_file
                try:
                    cache.record_success(output_file, result["parsed_by"])
                except OSError as error:
                    log_msg(f"  [WARNING] Markdown saved but completion record failed: {error}")
                    result["error_message"] = f"Completion record not saved: {error}"
            return result
    except Exception as error:
        log_msg(f"  [ERROR] Processing '{pdf_path}' failed: {error}")
        return {
            "symbol": symbol, "year": year,
            "file_name": os.path.basename(pdf_path), "status": "failed",
            "parsed_by": "none", "processing_time_sec": round(time.time() - started, 2),
            "error_message": str(error),
        }


def _convert_pdf_file(pdf_path, symbol, year, output_dir, source_hash):
    """
    Worker function: Converts PDF to Markdown with real-time step logging.
    """
    start_time = time.time()
    file_name = os.path.basename(pdf_path)
    report_period = classify_report_period(pdf_path)
    output_md_filename = markdown_filename(pdf_path, symbol, year, source_hash)
    output_md_path = os.path.join(output_dir, output_md_filename)

    log_msg(f"  --> [START FILE] Processing '{file_name}' ({symbol} | {year})")
    log_msg(f"      File size: {os.path.getsize(pdf_path) / (1024 * 1024):.2f} MB")

    md_content = None
    parsing_engine = "pymupdf4llm"
    error_message = ""

    # Primary Attempt: PyMuPDF4LLM
    log_msg(f"      [1/3 Engine] Invoking pymupdf4llm.to_markdown()...")
    try:
        engine_start = time.time()
        md_content = pymupdf4llm.to_markdown(pdf_path, write_images=False)
        engine_elapsed = round(time.time() - engine_start, 2)
        log_msg(f"      [1/3 Engine] pymupdf4llm completed in {engine_elapsed}s.")
    except Exception as primary_error:
        engine_elapsed = round(time.time() - engine_start, 2)
        log_msg(f"      [1/3 Engine FAIL] pymupdf4llm failed after {engine_elapsed}s: {primary_error}")
        log_msg(f"      [2/3 Engine] Switching to MarkItDown fallback...")
        
        # Fallback Attempt: MarkItDown
        try:
            fallback_start = time.time()
            md_converter = MarkItDown()
            conversion_result = md_converter.convert(pdf_path)
            md_content = conversion_result.text_content
            parsing_engine = "markitdown"
            fallback_elapsed = round(time.time() - fallback_start, 2)
            log_msg(f"      [2/3 Engine] MarkItDown completed in {fallback_elapsed}s.")
        except Exception as fallback_error:
            elapsed_time = round(time.time() - start_time, 2)
            error_message = f"pymupdf4llm: {primary_error} | markitdown: {fallback_error}"
            log_msg(f"  [ERROR] Both parsers failed for '{file_name}' after {elapsed_time}s.")
            return {
                "symbol": symbol,
                "year": year,
                "file_name": file_name,
                "status": "failed",
                "parsed_by": "none",
                "processing_time_sec": elapsed_time,
                "error_message": error_message
            }

    elapsed_time = round(time.time() - start_time, 2)

    if not md_content or not md_content.strip():
        log_msg(f"  [WARNING] Empty content extracted from '{file_name}' ({elapsed_time}s)")
        return {
            "symbol": symbol,
            "year": year,
            "file_name": file_name,
            "status": "failed",
            "parsed_by": parsing_engine,
            "processing_time_sec": elapsed_time,
            "error_message": "Empty content extracted"
        }

    # Construct YAML frontmatter
    log_msg(f"      [3/3 Save] Writing Markdown to disk ({len(md_content)} chars)...")
    source_path = pdf_path.replace("\\", "/")
    frontmatter = (
        f"---\n"
        f"symbol: \"{symbol}\"\n"
        f"year: \"{year}\"\n"
        f"report_period: \"{report_period}\"\n"
        f"file_name: \"{file_name}\"\n"
        f"source_path: \"{source_path}\"\n"
        f"document_type: \"{report_period if report_period != 'Unknown' else 'Financial'} Report\"\n"
        f"parsed_by: \"{parsing_engine}\"\n"
        f"---\n\n"
    )

    # Save to disk
    try:
        os.makedirs(output_dir, exist_ok=True)
        atomic_write(output_md_path, frontmatter + md_content)

        log_msg(f"  [SUCCESS] Saved '{output_md_filename}' using {parsing_engine} in {elapsed_time}s")
        return {
            "symbol": symbol,
            "year": year,
            "file_name": file_name,
            "status": "success",
            "parsed_by": parsing_engine,
            "processing_time_sec": elapsed_time,
            "error_message": ""
        }
    except Exception as e:
        log_msg(f"  [ERROR] Writing to disk failed for '{output_md_filename}': {e}")
        return {
            "symbol": symbol,
            "year": year,
            "file_name": file_name,
            "status": "failed",
            "parsed_by": parsing_engine,
            "processing_time_sec": elapsed_time,
            "error_message": str(e)
        }


def process_symbol_folder(symbol, use_multithreading=False, force=False):
    """
    Processes all PDFs for a company symbol with terminal logging.
    """
    symbol_dir = os.path.join(BASE_DIR, symbol)
    log_msg(f"==================================================")
    log_msg(f"Processing Symbol: {symbol}")
    log_msg(f"Directory path: {symbol_dir}")

    if not os.path.exists(symbol_dir) or not os.path.isdir(symbol_dir):
        log_msg(f"[SKIP] Directory for symbol '{symbol}' not found.")
        return [{
            "symbol": symbol,
            "year": "N/A",
            "file_name": "N/A",
            "status": "skipped",
            "parsed_by": "none",
            "processing_time_sec": 0,
            "error_message": f"Directory not found: {symbol_dir}"
        }]

    year_folders = [
        d for d in os.listdir(symbol_dir) 
        if os.path.isdir(os.path.join(symbol_dir, d))
    ]
    log_msg(f"Found {len(year_folders)} year subfolder(s): {year_folders}")

    if not year_folders:
        log_msg(f"[WARNING] No year subfolders found inside symbol directory: {symbol}")
        return [{
            "symbol": symbol,
            "year": "N/A",
            "file_name": "N/A",
            "status": "skipped",
            "parsed_by": "none",
            "processing_time_sec": 0,
            "error_message": "No year folders found"
        }]

    pdf_tasks = []
    for year in year_folders:
        year_path = os.path.join(symbol_dir, year)
        pdf_files = glob.glob(os.path.join(year_path, "*.pdf"))
        log_msg(f"  Year '{year}': Found {len(pdf_files)} PDF(s)")

        for pdf_path in pdf_files:
            pdf_tasks.append((pdf_path, symbol, year, OUTPUT_DIR))

    if not pdf_tasks:
        log_msg(f"[WARNING] No PDF files found in any year folder for symbol: {symbol}")
        return [{
            "symbol": symbol,
            "year": "N/A",
            "file_name": "N/A",
            "status": "skipped",
            "parsed_by": "none",
            "processing_time_sec": 0,
            "error_message": "No PDF files found in subfolders"
        }]

    mode_str = "Parallel" if use_multithreading else "Sequential"
    log_msg(f"Starting execution of {len(pdf_tasks)} task(s) in {mode_str} mode...")

    results = []

    if use_multithreading:
        num_workers = min(len(year_folders), 2)
        log_msg(f"Launching ThreadPoolExecutor with max_workers={num_workers}...")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(read_pdf_file, pdf_path, sym, yr, out_dir, force=force)
                for pdf_path, sym, yr, out_dir in pdf_tasks
            ]
            for idx, future in enumerate(futures, start=1):
                res = future.result()
                if res:
                    results.append(res)
                log_msg(f"  Progress: Completed {idx}/{len(futures)} tasks for {symbol}")
    else:
        for idx, (pdf_path, sym, yr, out_dir) in enumerate(pdf_tasks, start=1):
            log_msg(f"--- Task {idx}/{len(pdf_tasks)} for {symbol} ---")
            res = read_pdf_file(pdf_path, sym, yr, out_dir, force=force)
            if res:
                results.append(res)

    log_msg(f"Finished Symbol '{symbol}'. Processed {len(results)} document(s).\n")
    return results


def main(use_multithreading=False, force=False):
    """
    Main driver function with end-to-end logging.
    """
    log_msg("Pipeline execution initiated.")
    log_msg(f"Loading CSV from: '{CSV_FILE_PATH}'")

    if not os.path.exists(CSV_FILE_PATH):
        log_msg(f"CRITICAL ERROR: CSV file not found at '{CSV_FILE_PATH}'")
        return

    df = pd.read_csv(CSV_FILE_PATH)
    symbol_col = next((col for col in df.columns if col.strip().lower() == 'symbol'), None)

    if not symbol_col:
        log_msg("CRITICAL ERROR: CSV must contain a 'Symbol' column.")
        return

    symbols = df[symbol_col].dropna().astype(str).str.strip().tolist()
    log_msg(f"Successfully loaded {len(symbols)} symbol(s) from CSV: {symbols[:5]}...")

    all_summary_logs = []

    for idx, symbol in enumerate(symbols, start=1):
        log_msg(f"\n==========================================")
        log_msg(f"Global Progress: Symbol {idx}/{len(symbols)} -> {symbol}")
        log_msg(f"==========================================")

        try:
            symbol_results = process_symbol_folder(symbol, use_multithreading=use_multithreading, force=force)
            all_summary_logs.extend(symbol_results)
        except Exception as e:
            log_msg(f"[ERROR] Unexpected error processing symbol '{symbol}': {e}")
            all_summary_logs.append({
                "symbol": symbol,
                "year": "N/A",
                "file_name": "N/A",
                "status": "failed",
                "parsed_by": "none",
                "processing_time_sec": 0,
                "error_message": f"Unexpected symbol error: {str(e)}"
            })

    # Save CSV Summary Report
    log_msg("Generating final CSV summary report...")
    summary_df = pd.DataFrame(all_summary_logs)
    os.makedirs(os.path.dirname(SUMMARY_CSV_PATH), exist_ok=True)
    summary_df.to_csv(SUMMARY_CSV_PATH, index=False)

    if summary_df.empty:
        log_msg("No PDF files processed.")
        return
    successful = len(summary_df[summary_df["status"] == "success"])
    failed = len(summary_df[summary_df["status"] == "failed"])
    skipped = len(summary_df[summary_df["status"] == "skipped"])

    log_msg("==========================================")
    log_msg("ALL PROCESSING COMPLETE!")
    log_msg(f"Total Entries Logged : {len(summary_df)}")
    log_msg(f"  - Success          : {successful}")
    log_msg(f"  - Failed           : {failed}")
    log_msg(f"  - Skipped          : {skipped}")
    log_msg(f"Summary Report Saved : {SUMMARY_CSV_PATH}")
    log_msg("==========================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert annual-report PDFs to Markdown")
    parser.add_argument("--force", action="store_true", help="Reprocess even successfully converted PDFs")
    main(use_multithreading=False, force=parser.parse_args().force)

