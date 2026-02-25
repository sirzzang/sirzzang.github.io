#!/usr/bin/env python3
"""
Scan all Jekyll posts for internal links and generate a backlinks data file.

For each post that is linked by other posts, produces a list of
"referring" posts so the layout can display them as backlinks.

Handles three link patterns:
  1. {% post_url YYYY-MM-DD-Slug %}           (Jekyll Liquid tag)
  2. https://sirzzang.github.io/category/Slug/ (absolute URL)
  3. [text](/category/Slug/)                   (relative path in Markdown)

Usage:
    python3 _scripts/generate_backlinks.py
"""

import os
import re
import yaml
from pathlib import Path

POSTS_DIR = "_posts"
OUTPUT_FILE = os.path.join("_data", "backlinks.yml")
SITE_HOST = "sirzzang.github.io"

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

POST_URL_RE = re.compile(r"\{%\s*post_url\s+([\w-]+)\s*%\}")
FULL_URL_RE = re.compile(
    rf"https?://{re.escape(SITE_HOST)}(/[\w/-]+)"
)
RELATIVE_URL_RE = re.compile(r"\]\((/[a-z]+/[\w-]+/?)")


def parse_front_matter(content: str) -> dict:
    match = FRONT_MATTER_RE.match(content)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def slug_from_filename(filename: str) -> str:
    """'2026-01-23-Kubernetes-Swap.md' -> 'Kubernetes-Swap'"""
    stem = Path(filename).stem
    m = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", stem)
    return m.group(1) if m else stem


def permalink(categories: list[str], slug: str) -> str:
    cat = "/".join(c.lower() for c in categories) if categories else ""
    return f"/{cat}/{slug}/" if cat else f"/{slug}/"


def normalize(url: str) -> str:
    url = url.split("#")[0]
    url = url.rstrip("/")
    return url.lower() or "/"


def build_post_map(posts_dir: str):
    """First pass: map every post to its metadata.

    Returns
        slug_map  – date-slug  -> {url, title}  (for post_url resolution)
        url_map   – normalised URL -> {url, title}
    """
    slug_map: dict[str, dict] = {}
    url_map: dict[str, dict] = {}

    for fname in sorted(os.listdir(posts_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(posts_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()

        fm = parse_front_matter(content)
        cats = fm.get("categories", [])
        if isinstance(cats, str):
            cats = [cats]

        slug = slug_from_filename(fname)
        url = permalink(cats, slug)
        title = fm.get("title", slug)
        info = {"url": url, "title": title}

        date_slug = Path(fname).stem
        slug_map[date_slug] = info
        url_map[normalize(url)] = info

    return slug_map, url_map


def find_outgoing_links(content: str, slug_map: dict) -> set[str]:
    links: set[str] = set()

    for m in POST_URL_RE.finditer(content):
        date_slug = m.group(1)
        if date_slug in slug_map:
            links.add(normalize(slug_map[date_slug]["url"]))

    for m in FULL_URL_RE.finditer(content):
        links.add(normalize(m.group(1)))

    for m in RELATIVE_URL_RE.finditer(content):
        links.add(normalize(m.group(1)))

    return links


def build_backlinks(posts_dir: str, slug_map: dict, url_map: dict):
    backlinks: dict[str, list[dict]] = {}

    for fname in sorted(os.listdir(posts_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(posts_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()

        date_slug = Path(fname).stem
        source = slug_map.get(date_slug)
        if not source:
            continue
        source_norm = normalize(source["url"])

        for target_norm in find_outgoing_links(content, slug_map):
            if target_norm == source_norm:
                continue
            if target_norm not in url_map:
                continue
            backlinks.setdefault(target_norm, []).append(
                {"title": source["title"], "url": source["url"]}
            )

    return backlinks


def write_yaml(backlinks: dict, url_map: dict, output: str):
    """Write YAML keyed by the original (cased) URL."""
    result: dict[str, list[dict]] = {}
    for norm_url, sources in sorted(backlinks.items()):
        original_url = url_map[norm_url]["url"] if norm_url in url_map else norm_url
        seen = set()
        deduped = []
        for s in sorted(sources, key=lambda x: x["title"]):
            if s["url"] not in seen:
                seen.add(s["url"])
                deduped.append(s)
        result[original_url] = deduped

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        yaml.dump(result, f, allow_unicode=True, default_flow_style=False, sort_keys=True)

    return result


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    slug_map, url_map = build_post_map(POSTS_DIR)
    backlinks = build_backlinks(POSTS_DIR, slug_map, url_map)
    result = write_yaml(backlinks, url_map, OUTPUT_FILE)

    total_targets = len(result)
    total_refs = sum(len(v) for v in result.values())
    print(f"Backlinks generated: {total_targets} posts have backlinks ({total_refs} total references)")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
