#!/usr/bin/env python3
"""Generate apex-agents-harbor from Mercor's APEX-Agents 1.1 Harbor Hub release.

    harbor datasets download mercor/apex-agents-1-1@1.0.1 -o /tmp/hub --export
    python3 scripts/generate.py --source /tmp/hub/apex-agents-1-1 --hub-revision 14

Every task package is copied verbatim except for the three image references
(`[environment].docker_image` in task.toml, the world `image:` in
environment/docker-compose.yaml, and `FROM` in tests/Dockerfile), which are
repointed from Mercor's public ECR repository to the Osmosis mirror. The digests
are unchanged, so each reference still names the exact image Mercor published.

`--check` validates a checked-in tree instead of writing one. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_NAME = "apex-agents-1-1"
DATASET_VERSION = "1.0.1"
HUB_DATASET = f"mercor/{DATASET_NAME}@{DATASET_VERSION}"
HUGGINGFACE_DATASET = "mercor/apex-agents-v1.1"
SOURCE_REGISTRY = "public.ecr.aws/k4t1e3r5/harbor-hub"
MIRROR = "ghcr.io/osmosis-ai/apex-agents-1-1"
COMPANION_AGENT = (
    "Mercor-Intelligence/apex_loop_truncated_tools_agent"
    "@1ec75805084ca5b8aff1d6411e9e3cef03a46947"
)
TASK_COUNT = 240
DOMAINS = ("Investment Banking", "Law", "Management Consulting")
DESCRIPTION = (
    "APEX-Agents 1.1 (Mercor): 240 long-horizon professional-services tasks across "
    "investment banking, law, and management consulting, as published on the Harbor "
    "Hub, with the world, agent, and verifier images repointed to the Osmosis mirror "
    "at their original digests."
)
DIGEST = r"sha256:[0-9a-f]{64}"
SOURCE_REF = re.compile(rf"{re.escape(SOURCE_REGISTRY)}@({DIGEST})")


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def rewrite(text: str, registry: str, label: str) -> tuple[str, str]:
    """Replace the single image reference in `text`; return (new text, digest)."""
    pattern = re.compile(rf"{re.escape(registry)}@({DIGEST})")
    matches = pattern.findall(text)
    if len(matches) != 1:
        fail(f"{label}: expected one {registry} reference, found {len(matches)}")
    return pattern.sub(f"{MIRROR}@\\1", text), matches[0]


def task_files(task_dir: Path) -> dict[str, Path]:
    return {
        "task.toml": task_dir / "task.toml",
        "compose": task_dir / "environment" / "docker-compose.yaml",
        "dockerfile": task_dir / "tests" / "Dockerfile",
    }


def generate(source: Path, hub_revision: int) -> None:
    task_dirs = sorted(p for p in source.iterdir() if (p / "task.toml").is_file())
    if len(task_dirs) != TASK_COUNT:
        fail(f"expected {TASK_COUNT} task directories under {source}, found {len(task_dirs)}")
    tasks_root = ROOT / "tasks"
    if tasks_root.exists():
        shutil.rmtree(tasks_root)
    tasks_root.mkdir()

    worlds: dict[str, dict] = {}
    roles: dict[str, set[str]] = {"agent": set(), "verifier": set()}
    domains: Counter[str] = Counter()
    snapshot_tasks = 0
    registry_tasks = []
    for src in task_dirs:
        slug = src.name
        dst = tasks_root / slug
        shutil.copytree(src, dst)
        files = task_files(dst)
        config = tomllib.loads(files["task.toml"].read_text())
        if config["task"]["name"] != f"mercor/{slug}":
            fail(f"{slug}: task.toml name {config['task']['name']!r} is not mercor/{slug}")
        metadata = config["metadata"]
        domains[metadata["domain"]] += 1
        if (dst / "tests" / "needs_snapshot").exists():
            snapshot_tasks += 1

        toml_text, agent_digest = rewrite(files["task.toml"].read_text(), SOURCE_REGISTRY, f"{slug}/task.toml")
        compose_text, world_digest = rewrite(files["compose"].read_text(), SOURCE_REGISTRY, f"{slug}/docker-compose.yaml")
        docker_text, verifier_digest = rewrite(files["dockerfile"].read_text(), SOURCE_REGISTRY, f"{slug}/tests/Dockerfile")
        files["task.toml"].write_text(toml_text)
        files["compose"].write_text(compose_text)
        files["dockerfile"].write_text(docker_text)
        roles["agent"].add(agent_digest)
        roles["verifier"].add(verifier_digest)
        world = worlds.setdefault(
            metadata["world_id"],
            {"digest": world_digest, "world_slug": metadata["world_slug"], "domain": metadata["domain"], "task_count": 0},
        )
        if world["digest"] != world_digest:
            fail(f"{slug}: world {metadata['world_id']} has two image digests")
        world["task_count"] += 1
        registry_tasks.append({"name": slug, "path": f"tasks/{slug}"})

    for role, digests in roles.items():
        if len(digests) != 1:
            fail(f"expected one shared {role} image, found {len(digests)}")
    if set(domains) != set(DOMAINS):
        fail(f"unexpected domains {sorted(domains)}")

    def short(world_id: str) -> str:
        return world_id.removeprefix("world_")[:12]

    images = {
        "source_registry": SOURCE_REGISTRY,
        "mirror": MIRROR,
        "platform": "linux/amd64",
        "agent": {"tag": "agent", "digest": next(iter(roles["agent"]))},
        "verifier": {"tag": "verifier", "digest": next(iter(roles["verifier"]))},
        "worlds": {
            world_id: {"tag": f"world-{short(world_id)}", **world}
            for world_id, world in sorted(worlds.items())
        },
    }
    manifest = {
        "schema_version": 1,
        "dataset": {"name": DATASET_NAME, "version": DATASET_VERSION, "task_count": TASK_COUNT},
        "upstream": {
            "harbor_hub_dataset": HUB_DATASET,
            "harbor_hub_revision": hub_revision,
            "huggingface_dataset": HUGGINGFACE_DATASET,
            "publisher": "Mercor",
            "license": "CC-BY-4.0",
            "terms": "Evaluation only; training, fine-tuning, or parameter fitting on the benchmark is forbidden by the publisher.",
        },
        "companion_agent": {"repository": COMPANION_AGENT.split("@")[0], "commit": COMPANION_AGENT.split("@")[1]},
        "changes_from_upstream": [
            "[environment].docker_image in task.toml repointed to the mirror (same digest)",
            "world image in environment/docker-compose.yaml repointed to the mirror (same digest)",
            "FROM in tests/Dockerfile repointed to the mirror (same digest)",
        ],
        "harbor_task_name_prefix": "mercor/",
        "result_task_name_prefix": None,
        "domains": dict(sorted(domains.items())),
        "snapshot_tasks": snapshot_tasks,
        "images": images,
    }
    (ROOT / "manifests").mkdir(exist_ok=True)
    (ROOT / "manifests" / f"{DATASET_NAME}-{DATASET_VERSION}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "registry.json").write_text(
        json.dumps([{"name": DATASET_NAME, "version": DATASET_VERSION, "description": DESCRIPTION, "tasks": registry_tasks}], indent=2) + "\n"
    )
    print(f"wrote {TASK_COUNT} tasks, {len(worlds)} world images, {snapshot_tasks} snapshot tasks")


def check() -> None:
    manifest = json.loads((ROOT / "manifests" / f"{DATASET_NAME}-{DATASET_VERSION}.json").read_text())
    [registry] = json.loads((ROOT / "registry.json").read_text())
    listed = {task["name"]: task["path"] for task in registry["tasks"]}
    on_disk = sorted(p.name for p in (ROOT / "tasks").iterdir() if p.is_dir())
    if sorted(listed) != on_disk or len(on_disk) != TASK_COUNT:
        fail("registry.json does not list exactly the tasks/ directories")
    images = manifest["images"]
    worlds = {w["digest"] for w in images["worlds"].values()}
    problems = []
    for slug, path in listed.items():
        if path != f"tasks/{slug}":
            problems.append(f"{slug}: path {path}")
        files = task_files(ROOT / path)
        for label, digest_set in (("task.toml", {images["agent"]["digest"]}), ("compose", worlds), ("dockerfile", {images["verifier"]["digest"]})):
            text = files[label].read_text()
            refs = re.findall(rf"{re.escape(MIRROR)}@({DIGEST})", text)
            if len(refs) != 1 or refs[0] not in digest_set:
                problems.append(f"{slug}/{label}: mirror reference {refs}")
            if SOURCE_REGISTRY in text:
                problems.append(f"{slug}/{label}: still references {SOURCE_REGISTRY}")
    if problems:
        fail("\n".join(problems[:20]))
    print(f"ok: {len(on_disk)} tasks reference the mirror at the recorded digests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, help="directory holding the 240 Hub task directories")
    parser.add_argument("--hub-revision", type=int, help="Harbor Hub revision the packages were downloaded from")
    parser.add_argument("--check", action="store_true", help="validate the checked-in tree")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.source and args.hub_revision is not None:
        generate(args.source.resolve(), args.hub_revision)
        check()
    else:
        parser.error("pass --source and --hub-revision, or --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
