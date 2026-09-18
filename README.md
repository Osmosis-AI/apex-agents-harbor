# apex-agents-harbor

Mercor's [APEX-Agents 1.1](https://huggingface.co/datasets/mercor/apex-agents-v1.1) benchmark as Harbor tasks, taken from the Harbor Hub release `mercor/apex-agents-1-1@1.0.1` and changed in exactly one way: the three image references in every task package point at `ghcr.io/osmosis-ai/apex-agents-1-1` instead of Mercor's `public.ecr.aws/k4t1e3r5/harbor-hub`, **at their original digests**. Nothing else is edited; instructions, rubrics, gold outputs, world seeds, and the companion-agent configuration are Mercor's bytes.

Why a mirror: the Osmosis runner pulls images anonymously from inside Daytona sandboxes, and Amazon ECR Public caps anonymous pulls at 1 per second and 500 GB per month. Each APEX trial pulls about 3.4 GB, so a concurrent or full run exceeds both. GitHub Container Registry has no such cap for public packages.

## Status

`v1.0.1` mirrors Hub revision 14 of `mercor/apex-agents-1-1@1.0.1`: 240 tasks over 31 worlds (80 each in investment banking, law, and management consulting), 34 of them file-output tasks graded from world snapshots. Companion agent of record: `Mercor-Intelligence/apex_loop_truncated_tools_agent@1ec75805084ca5b8aff1d6411e9e3cef03a46947` (the commit whose system prompt matches the release's `agent.json`). `manifests/apex-agents-1-1-1.0.1.json` records every digest.

| Pin | Value |
| --- | --- |
| Upstream | Harbor Hub `mercor/apex-agents-1-1@1.0.1`, revision 14 (Hugging Face `mercor/apex-agents-v1.1`) |
| Agent image (main container) | `ghcr.io/osmosis-ai/apex-agents-1-1@sha256:9be28bae20bc6027715df7f81e1d725d5c85dd3edd6669f8736a6a575a0bbcc2` |
| Verifier base image | `ghcr.io/osmosis-ai/apex-agents-1-1@sha256:19f9601e17b39a6c8c20a86971c296a915600e3cdd127c35957704cdd80591b2` |
| World images | 31, one per world, listed in the manifest under `images.worlds` |
| Judge | Pinned by every task's `tests/grading_config.json`: `fireworks_ai/accounts/fireworks/models/deepseek-v4-flash-0731`, temperature 0.1 |

## Layout

```
registry.json                       one dataset entry, apex-agents-1-1@1.0.1; task items are {name, path}
tasks/<slug>/                       Mercor's task package, image references repointed
manifests/apex-agents-1-1-<v>.json  upstream pins, companion agent, every image digest and mirror tag
scripts/generate.py                 rebuild tasks/, registry.json and the manifest from a Hub download; --check validates
scripts/mirror.py                   crane-copy every image to the mirror and verify digests; --check verifies only
```

Task names in `task.toml` stay `mercor/<slug>`, so Harbor reports the same task ids as a Hub run; selection is by directory name.

## Regenerating

```bash
uv tool install harbor
harbor datasets download mercor/apex-agents-1-1@1.0.1 -o /tmp/hub --export
python3 scripts/generate.py --source /tmp/hub/apex-agents-1-1 --hub-revision <revision harbor printed>
```

Then run the `mirror-images` workflow (or `scripts/mirror.py` with `crane` logged into ghcr.io) so every digest the tree references is served by the mirror, and tag the commit `v<version>`.

## License and terms

The task packages are Mercor's, under CC BY 4.0; see `LICENSE` for attribution and the publisher's evaluation-only terms. Do not use the tasks, rubrics, gold outputs, or run traces for training.
