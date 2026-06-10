#!/usr/bin/env python3
"""CLI entrypoint for running an offline SI v2 episode.

Usage:
    python self_improvement_v2/run_offline_episode.py

Outputs a deterministic YAML/JSON result to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from si_v2.episode.offline_episode import OfflineEpisode


def main() -> int:
    episode = OfflineEpisode(root=Path("self_improvement_v2"))
    result = episode.run()

    output = json.dumps(result.to_dict(), indent=2)
    print(output)

    if result.verdict.value == "red":
        return 1
    elif result.verdict.value == "yellow":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
