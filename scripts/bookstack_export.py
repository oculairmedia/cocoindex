"""
BookStack -> JSON export script for CocoIndex ingestion

Reads BookStack API and writes one JSON file per page into ./bookstack_export/
Required env vars:
  BS_URL, BS_TOKEN_ID, BS_TOKEN_SECRET
Optional env:
  OUT_DIR (default: ./bookstack_export)

This script does not run automatically. Execute manually when ready, e.g.:
  python scripts/bookstack_export.py --limit 100

Dependencies (not installed here): requests
"""
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


def getenv_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def api_session() -> requests.Session:
    base = getenv_required("BS_URL").rstrip("/")
    token_id = getenv_required("BS_TOKEN_ID")
    token_secret = getenv_required("BS_TOKEN_SECRET")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Token {token_id}:{token_secret}",
        "Accept": "application/json",
        "User-Agent": "cocoindex-bookstack-export/1.0",
    })
    s.base_url = base  # type: ignore[attr-defined]
    return s


def list_pages(s: requests.Session, count: int = 100) -> Iterable[Dict[str, Any]]:
    """Yield page summaries using pagination.
    BookStack supports /api/pages?count=...&offset=...
    """
    offset = 0
    while True:
        url = f"{s.base_url}/api/pages"  # type: ignore[attr-defined]
        r = s.get(url, params={"count": count, "offset": offset}, timeout=30)
        r.raise_for_status()
        data = r.json()
        pages = data if isinstance(data, list) else data.get("data", [])
        if not pages:
            break
        for p in pages:
            yield p
        offset += len(pages)


def get_page_detail(s: requests.Session, page_id: int) -> Dict[str, Any]:
    # include related data if available
    url = f"{s.base_url}/api/pages/{page_id}"  # type: ignore[attr-defined]
    r = s.get(url, params={"include": "book,chapter,tags"}, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_output(page: Dict[str, Any]) -> Dict[str, Any]:
    # BookStack fields vary slightly by version. Be defensive.
    pid = page.get("id") or page.get("page_id")
    title = page.get("name") or page.get("title") or f"Page {pid}"
    slug = page.get("slug")
    url = page.get("url") or page.get("_url") or f"{os.getenv('BS_URL','').rstrip('/')}/page/{pid}"
    updated_at = page.get("updated_at") or page.get("last_updated")
    body_html = page.get("html") or page.get("body_html") or page.get("content_html") or ""

    # Related
    book = None
    if isinstance(page.get("book"), dict):
        book = page["book"].get("name") or page["book"].get("slug")
    chapter = None
    if isinstance(page.get("chapter"), dict):
        chapter = page["chapter"].get("name") or page["chapter"].get("slug")

    # Tags: BookStack tags can have name/value pairs
    tags_list: List[str] = []
    for t in page.get("tags") or []:
        name = (t.get("name") or "").strip()
        value = (t.get("value") or "").strip()
        if name and value:
            tags_list.append(f"{name}:{value}")
        elif name:
            tags_list.append(name)

    return {
        "id": pid,
        "title": title,
        "slug": slug,
        "url": url,
        "updated_at": updated_at,
        "body_html": body_html,
        "tags": tags_list,
        "book": book,
        "chapter": chapter,
    }


def write_json(out_dir: Path, page_id: int, data: Dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"page_{page_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export BookStack pages to JSON files")
    parser.add_argument("--limit", type=int, default=None, help="Max pages to export")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between requests (s)")
    parser.add_argument("--out", default=os.getenv("OUT_DIR", "bookstack_export"), help="Output directory")
    args = parser.parse_args()

    s = api_session()
    out_dir = Path(args.out)

    exported = 0
    for summary in list_pages(s):
        pid = summary.get("id")
        if pid is None:
            continue
        detail = get_page_detail(s, int(pid))
        out = extract_output(detail)
        write_json(out_dir, int(pid), out)
        exported += 1
        if args.sleep:
            time.sleep(args.sleep)
        if args.limit and exported >= args.limit:
            break

    print(f"Exported {exported} page(s) to {out_dir}")


if __name__ == "__main__":
    main()

