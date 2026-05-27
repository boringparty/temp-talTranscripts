#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md


def clean_markdown(markdown: str) -> str:
    """
    Light cleanup after HTML -> Markdown conversion.
    Keeps links intact, but removes excessive blank lines and whitespace.
    """
    markdown = markdown.replace("\xa0", " ")

    # Remove trailing whitespace.
    markdown = "\n".join(line.rstrip() for line in markdown.splitlines())

    # Collapse 3+ blank lines into 2.
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    return markdown.strip() + "\n"


def extract_main_html(html: str) -> str:
    """
    Try to isolate the useful transcript content.

    If the site markup changes, this falls back to the full <body>.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove junk that almost never belongs in readable Markdown.
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # These selectors are intentionally broad/fallback-ish.
    candidates = [
        "main",
        "article",
        ".transcript",
        ".field-name-body",
        ".content",
        "#content",
    ]

    for selector in candidates:
        found = soup.select_one(selector)
        if found and found.get_text(strip=True):
            return str(found)

    body = soup.body
    if body and body.get_text(strip=True):
        return str(body)

    return html


def html_to_markdown(html: str) -> str:
    main_html = extract_main_html(html)

    markdown = md(
        main_html,
        heading_style="ATX",
        bullets="-",
        strip=[
            "img",
            "picture",
            "source",
            "iframe",
            "form",
            "button",
            "input",
            "textarea",
            "select",
        ],
    )

    return clean_markdown(markdown)


def append_log(
    log_path: Path,
    source_file: Path,
    output_file: Path | None,
    status: str,
    message: str = "",
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = log_path.exists()

    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp_utc",
                "source_file",
                "output_file",
                "status",
                "message",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source_file": str(source_file),
                "output_file": str(output_file) if output_file else "",
                "status": status,
                "message": message,
            }
        )


def convert_all(
    input_dir: Path,
    output_dir: Path,
    overwrite: bool,
) -> None:
    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "conversion-log.csv"

    source_files = sorted(input_dir.glob("*.txt"))

    if not source_files:
        print(f"No .txt files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    converted = 0
    skipped = 0
    errors = 0

    for source_path in source_files:
        output_path = output_dir / f"{source_path.stem}.md"

        try:
            if output_path.exists() and not overwrite:
                print(f"Skip {source_path.name}: {output_path.name} already exists")
                append_log(
                    log_path=log_path,
                    source_file=source_path,
                    output_file=output_path,
                    status="skipped",
                    message="Markdown file already exists",
                )
                skipped += 1
                continue

            print(f"Convert {source_path.name} -> {output_path.name}")

            html = source_path.read_text(encoding="utf-8", errors="replace")
            markdown = html_to_markdown(html)

            output_path.write_text(markdown, encoding="utf-8")

            append_log(
                log_path=log_path,
                source_file=source_path,
                output_file=output_path,
                status="converted",
            )

            converted += 1

        except Exception as exc:
            print(f"ERROR converting {source_path}: {exc}", file=sys.stderr)

            append_log(
                log_path=log_path,
                source_file=source_path,
                output_file=output_path,
                status="error",
                message=str(exc),
            )

            errors += 1

    print()
    print(f"Done. Converted: {converted}, skipped: {skipped}, errors: {errors}")
    print(f"Log: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert saved TAL transcript HTML files to Markdown."
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory containing saved transcript .txt files. Default: transcripts",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("markdown"),
        help="Directory for generated Markdown files. Default: markdown",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing Markdown files.",
    )

    args = parser.parse_args()

    convert_all(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
