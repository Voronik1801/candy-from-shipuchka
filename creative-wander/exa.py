#!/usr/bin/env python3
"""Exa search — outside context and fact-checking for creative-wander.

Why not just web search: Exa matches on meaning rather than keywords, and can
filter by publication date and source type. Those are the two things this
method needs — "what came out in the last fortnight" and "give me papers, not
blogs retelling each other".

Needs a key:
    export EXA_API_KEY=...        # https://dashboard.exa.ai/api-keys
Put it in the environment, or in a .env file at the repo root.

    python3 exa.py news "Anthropic OpenAI releases" --days 14
    python3 exa.py fact "Eric Yuan left Cisco to found Zoom" --results 8
    python3 exa.py fact "..." --papers        # research papers only
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_URL = "https://api.exa.ai/search"


def load_key():
    key = os.environ.get("EXA_API_KEY")
    if key:
        return key
    # fallback: a .env at the repo root
    env_path = Path(os.environ.get("WANDER_ROOT", Path.cwd())) / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("EXA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def search(key, query, num_results, days=None, category=None):
    payload = {
        "query": query,
        "numResults": num_results,
        "contents": {"text": {"maxCharacters": 1200}, "highlights": True},
    }
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        payload["startPublishedDate"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if category:
        payload["category"] = category

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")[:400]
        sys.exit(f"Exa returned {err.code}: {body}")
    except urllib.error.URLError as err:
        sys.exit(f"Could not reach Exa: {err.reason}")


def render(data, query):
    results = data.get("results", [])
    print(f"# Exa: {query}")
    print(f"\nFound: {len(results)}\n")
    for i, item in enumerate(results, 1):
        print(f"## {i}. {item.get('title') or 'untitled'}")
        print(f"{item.get('url', '')}")
        published = item.get("publishedDate")
        author = item.get("author")
        meta = " · ".join(filter(None, [published, author]))
        if meta:
            print(f"*{meta}*")
        highlights = item.get("highlights") or []
        if highlights:
            print()
            for h in highlights[:2]:
                print(f"> {h.strip()}")
        elif item.get("text"):
            print()
            print(item["text"].strip()[:600])
        print()


def main():
    parser = argparse.ArgumentParser(description="Exa search")
    parser.add_argument("mode", choices=["news", "fact"],
                        help="news — recent items in a window; fact — verify a claim")
    parser.add_argument("query")
    parser.add_argument("--days", type=int, default=None,
                        help="only items from the last N days (news defaults to 14)")
    parser.add_argument("--results", type=int, default=8)
    parser.add_argument("--papers", action="store_true",
                        help="search research papers only")
    args = parser.parse_args()

    key = load_key()
    if not key:
        sys.exit(
            "No EXA_API_KEY. Get one at https://dashboard.exa.ai/api-keys\n"
            "Set it in the environment, or add EXA_API_KEY=... to .env\n"
            "Without a key, use your agent's built-in web search — it works too, "
            "it just filters by recency less well."
        )

    if args.mode == "news":
        days = args.days if args.days is not None else 14
        category = "news"
    else:
        days = args.days
        category = "research paper" if args.papers else None

    data = search(key, args.query, args.results, days=days, category=category)
    render(data, args.query)


if __name__ == "__main__":
    main()
