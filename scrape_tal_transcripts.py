#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


EPISODE_RE = re.compile(r"/(\d{1,4})(?:/|$)")


def make_session() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "tal-transcript-archiver/1.0"
    })

    return session


def read_urls(path: Path) -> list[str]:
    urls = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        urls.append(line)

    return urls


def get_episode_number(url: str) -> str:
    parsed = urlparse(url)
    match = EPISODE_RE.search(parsed.path)

    if not match:
        raise ValueError(f"Could not find episode number in URL: {url}")

    return match.group(1).zfill(3)


def fetch_html(session: requests.Session, url: str, timeout: int) -> tuple[str, int]:
    response = session.get(url, timeout=timeout)

    if response.status_code >= 400:
        raise requests.HTTPError(
            f"HTTP {response.status_code} for {url}",
            response=response,
        )

    return response.text, response.status_code


def append_log(
    log_path: Path,
    episode: str,
    url: str,
    output_file: str,
    status: str,
    http_status: str = "",
    bytes_written: int = 0,
    message: str = "",
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = log_path.exists()

    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp_utc",
                "episode",
                "url",
                "output_file",
                "status",
                "http_status",
                "bytes_written",
                "message",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "episode": episode,
            "url": url,
            "output_file": output_file,
            "status": status,
            "http_status": http_status,
            "bytes_written": bytes_written,
            "message": message,
        })


def scrape(
    urls: list[str],
    output_dir: Path,
    delay: float,
    timeout: int,
    overwrite: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "scrape-log.csv"
    session = make_session()

    saved = 0
    skipped = 0
    errors = 0

    for index, url in enumerate(urls, start=1):
        episode = ""

        try:
            episode = get_episode_number(url)
            output_path = output_dir / f"{episode}.txt"

            if output_path.exists() and not overwrite:
                print(f"[{index}/{len(urls)}] Skip {episode}: already exists")

                append_log(
                    log_path=log_path,
                    episode=episode,
                    url=url,
                    output_file=str(output_path),
                    status="skipped",
                    message="File already exists",
                )

                skipped += 1
                continue

            print(f"[{index}/{len(urls)}] Fetch {episode}: {url}")

            html, http_status = fetch_html(session, url, timeout=timeout)
            output_path.write_text(html, encoding="utf-8")

            bytes_written = output_path.stat().st_size

            append_log(
                log_path=log_path,
                episode=episode,
                url=url,
                output_file=str(output_path),
                status="saved",
                http_status=str(http_status),
                bytes_written=bytes_written,
            )

            saved += 1

            if delay > 0:
                time.sleep(delay)

        except Exception as exc:
            print(f"ERROR: {url} — {exc}", file=sys.stderr)

            append_log(
                log_path=log_path,
                episode=episode,
                url=url,
                output_file="",
                status="error",
                message=str(exc),
            )

            errors += 1

    print()
    print(f"Done. Saved: {saved}, skipped: {skipped}, errors: {errors}")
    print(f"Log: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--url-file",
        type=Path,
        default=Path("urls.txt"),
        help="URL list. Default: urls.txt",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../transcripts"),
        help="Output directory. Default: ../transcripts",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay between requests. Default: 1.5 seconds",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout. Default: 30 seconds",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing transcript files",
    )

    args = parser.parse_args()

    urls = read_urls(args.url_file)

    if not urls:
        print(f"No URLs found in {args.url_file}", file=sys.stderr)
        sys.exit(1)

    scrape(
        urls=urls,
        output_dir=args.output_dir,
        delay=args.delay,
        timeout=args.timeout,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
