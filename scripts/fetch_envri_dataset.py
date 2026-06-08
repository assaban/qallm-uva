#!/usr/bin/env python3
"""Fetch the ENVRI notebook validation set (Li's dataset) by search term.

Li's validation set is not committed anywhere; it is assembled at run time by
searching the ENVRI notebook catalogue (search.envri.eu) for a term and
cloning the GitHub repositories behind the results. This script reproduces
that, parameterised and resumable, so the validation corpus can be rebuilt
on the VM.

This is a network-heavy operation (it clones many repositories) and depends on
an external service whose results change over time, so the corpus is not
perfectly reproducible across dates. Record the term, page count, and date with
any results built from it.

Usage:
    python scripts/fetch_envri_dataset.py --term forest --pages 43 --output datasets/envri_forest
    python scripts/fetch_envri_dataset.py --term ocean  --pages 21 --output datasets/envri_ocean

Requires: requests, beautifulsoup4 (install with: pip install requests beautifulsoup4).
"""

import argparse
import subprocess
import sys
from pathlib import Path

# BASE_URL = "https://search.envri.eu/notebookSearch/genericsearch"
BASE_URL = "https://search.envri.eu/search/webSearch/genericsearch"


def fetch(term: str, pages: int, output: Path) -> int:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit(
            "This script needs requests and beautifulsoup4:\n"
            "  pip install requests beautifulsoup4"
        )

    output.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    cloned = 0
    failed = 0

    for page in range(1, pages + 1):
        url = f"{BASE_URL}?term={term}&page={page}"
        print(f"Scanning page {page}/{pages} ...")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001 - one bad page should not stop the crawl
            print(f"  page {page} failed: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            if not href.startswith("https://github.com/"):
                continue
            if href in seen:
                continue
            seen.add(href)

            repo_name = href.rstrip("/").rsplit("/", 1)[-1]
            dest = output / repo_name
            if dest.exists():
                print(f"  exists, skipping: {repo_name}")
                continue
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", href, str(dest)],
                    check=True, capture_output=True,
                )
                cloned += 1
                print(f"  cloned: {repo_name}")
            except subprocess.CalledProcessError as e:
                failed += 1
                print(f"  failed: {repo_name}: {e}")

    print(
        f"\nDone. term={term!r} pages={pages} cloned={cloned} failed={failed} "
        f"into {output}"
    )
    # A small provenance record so results can cite exactly what was fetched.
    (output / "_provenance.txt").write_text(
        f"term={term}\npages={pages}\ncloned={cloned}\nfailed={failed}\n"
        f"source={BASE_URL}\n",
        encoding="utf-8",
    )
    return cloned


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--term", required=True, help="ENVRI search term, e.g. forest, ocean.")
    p.add_argument("--pages", type=int, default=20, help="Result pages to scan.")
    p.add_argument("--output", required=True, help="Directory to clone into.")
    args = p.parse_args()
    fetch(args.term, args.pages, Path(args.output))


if __name__ == "__main__":
    main()
