#!/usr/bin/env python3
"""Copy the release's images from Mercor's public ECR to the Osmosis mirror.

    python3 scripts/mirror.py            # copy every image listed in the manifest
    python3 scripts/mirror.py --check    # only verify the mirror serves each digest

Needs `crane` on PATH; the workflow logs it into ghcr.io first. `crane copy`
transfers the manifest byte for byte, so the mirrored digest equals the source
digest, and every copy is verified against the manifest. Amazon ECR Public
allows one anonymous pull per second, so copies run sequentially with backoff.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    [registry] = json.loads((ROOT / "registry.json").read_text())
    path = ROOT / "manifests" / f"{registry['name']}-{registry['version']}.json"
    return json.loads(path.read_text())


def crane(*args: str, retries: int = 6) -> str:
    delay = 5.0
    for attempt in range(retries):
        result = subprocess.run(["crane", *args], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        if attempt == retries - 1:
            raise SystemExit(f"crane {' '.join(args)} failed:\n{result.stderr.strip()}")
        print(f"  retry in {delay:.0f}s: {result.stderr.strip()[-200:]}", file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def images(data: dict) -> list[tuple[str, str]]:
    section = data["images"]
    items = [(section["agent"]["tag"], section["agent"]["digest"]), (section["verifier"]["tag"], section["verifier"]["digest"])]
    items.extend((world["tag"], world["digest"]) for world in section["worlds"].values())
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify only; copy nothing")
    args = parser.parse_args()
    data = manifest()
    source, mirror = data["images"]["source_registry"], data["images"]["mirror"]
    failures = []
    for tag, digest in images(data):
        target = f"{mirror}:{tag}"
        if not args.check:
            print(f"copy {source}@{digest[:19]}... -> {target}", flush=True)
            crane("copy", f"{source}@{digest}", target)
        served = crane("digest", target)
        status = "ok" if served == digest else f"MISMATCH ({served})"
        print(f"  {target} {digest[:19]}... {status}", flush=True)
        if served != digest:
            failures.append(target)
    if failures:
        raise SystemExit(f"{len(failures)} mirrored image(s) do not match the manifest: {failures}")
    print(f"{len(images(data))} images verified at {mirror}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
