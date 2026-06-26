#!/usr/bin/env python3
"""Auto-set context_length in Hermes profile configs based on model cache.

Reads each profile's configured model, looks up its context limit in
models_dev_cache.json, and updates config.yaml if needed.

Usage:
    python3 auto_context_length.py                    # all profiles
    python3 auto_context_length.py orchestrator       # single profile
    python3 auto_context_length.py --check            # dry-run, show diffs only
"""

import json
import os
import re
import sys

HERMES_DIR = "/home/hermes/.hermes"
CACHE_PATH = os.path.join(HERMES_DIR, "models_dev_cache.json")
PROFILES_DIR = os.path.join(HERMES_DIR, "profiles")

# ── Model → Provider → Context Lookup ──────────────────────────

def load_cache():
    """Load models_dev_cache.json and build a lookup: (provider_key, model_id) -> context_limit."""
    if not os.path.exists(CACHE_PATH):
        print(f"ERROR: Cache not found at {CACHE_PATH}")
        sys.exit(1)

    with open(CACHE_PATH) as f:
        data = json.load(f)

    # Build lookup: { (provider_prefix, model_id): context }
    lookup = {}
    for provider_key, provider_val in data.items():
        if not isinstance(provider_val, dict):
            continue
        models = provider_val.get("models", {})
        if not models:
            # Maybe the provider entry itself has a limit (flat structure)
            limit = provider_val.get("limit", {})
            ctx = limit.get("context")
            if ctx:
                model_id = provider_val.get("id", provider_key.split("/")[-1])
                lookup[(provider_key, model_id)] = ctx
            continue

        for model_id, model_val in models.items():
            if not isinstance(model_val, dict):
                continue
            limit = model_val.get("limit", {})
            ctx = limit.get("context")
            if ctx and isinstance(ctx, int):
                lookup[(provider_key, model_id)] = ctx

    return lookup


def find_context(profile_name, profile_config, cache_lookup):
    """Find the correct context_length for a profile's model via its provider.

    Strategy:
    1. Get model.default and model.provider from the profile config.
    2. Normalize the provider name (handle dashes/underscores).
    3. Try exact match first: (provider, model_id)
    4. Fall back to fuzzy: find any entry where provider key *contains* the profile's provider
       AND model_id *contains* or *is contained in* the profile's model name.
    5. Last resort: search across all providers for model name match.
    """
    model_name = profile_config.get("model", {}).get("default", "")
    provider = profile_config.get("model", {}).get("provider", "")
    base_url = profile_config.get("model", {}).get("base_url", "")

    if not model_name or not provider:
        return None, "no model or provider configured"

    # Normalize: strip :cloud, :thinking suffixes for matching
    base_model = re.sub(r":[a-z-]+$", "", model_name)

    candidates = []

    for (pkey, mid), ctx in cache_lookup.items():
        # Exact provider match
        if pkey == provider and mid == model_name:
            return ctx, f"exact match {provider}/{model_name}"

        # Provider contains the profile provider, and model matches
        if provider in pkey or pkey in provider:
            if mid == model_name or mid == base_model or base_model in mid or mid in base_model:
                candidates.append((ctx, f"{pkey}/{mid}"))

        # Also check model base name against provider entry names
        if "/" not in pkey:  # non-nested provider
            if mid == model_name:
                candidates.append((ctx, f"{pkey}/{mid}"))

    if candidates:
        # Return highest context (most generous reading)
        best = max(candidates, key=lambda c: c[0])
        return best

    # Ultra-fuzzy: search all providers for any model matching
    for (pkey, mid), ctx in cache_lookup.items():
        if mid == model_name or mid == base_model:
            return ctx, f"fuzzy match via {pkey}/{mid}"

    return None, f"no match found for {provider}/{model_name}"


# ── Config File I/O ────────────────────────────────────────────

def read_config(profile_dir):
    """Read a profile's config.yaml, return (lines, model_section) or None."""
    config_path = os.path.join(profile_dir, "config.yaml")
    if not os.path.exists(config_path):
        return None, None, None

    with open(config_path) as f:
        content = f.read()

    # Parse YAML-ish model section
    model_match = re.search(
        r"^model:\s*\n(?:  .+\n?)*",
        content,
        re.MULTILINE
    )
    if not model_match:
        return content, None, config_path

    # Extract model.default and model.provider
    default_match = re.search(r"^\s{2}default:\s*(.+)", model_match.group(0), re.MULTILINE)
    provider_match = re.search(r"^\s{2}provider:\s*(.+)", model_match.group(0), re.MULTILINE)

    config = {
        "model": {
            "default": default_match.group(1).strip() if default_match else "",
            "provider": provider_match.group(1).strip() if provider_match else "",
        }
    }

    return content, config, config_path


def update_context_length(config_path, content, new_value, dry_run=False):
    """Update context_length in config.yaml content."""
    pattern = r"^(\s{2}context_length:\s*)\d+"
    replacement = f"\\1{new_value}"

    if not re.search(pattern, content, re.MULTILINE):
        # context_length doesn't exist yet — add it after the provider/base_url line
        # Find the end of the model section
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("default:") or stripped.startswith("provider:") or stripped.startswith("base_url:") or stripped.startswith("api_mode:"):
                continue
            if stripped.startswith("providers:") or (stripped and not line.startswith(" ")):
                # Insert before this line
                indent = "  "
                lines.insert(i, f"{indent}context_length: {new_value}")
                new_content = "\n".join(lines)
                break
        else:
            print(f"  ⚠️  Could not find insertion point in {config_path}")
            return False
    else:
        new_content = re.sub(pattern, replacement, content, count=1)

    if new_content == content:
        print(f"  ⚠️  No change needed in {config_path}")
        return False

    if dry_run:
        print(f"  📝 Would update: context_length → {new_value}")
        return True

    with open(config_path, "w") as f:
        f.write(new_content)
    print(f"  ✅ Updated: context_length → {new_value}")
    return True


# ── Main ────────────────────────────────────────────────────────

def main():
    dry_run = "--check" in sys.argv
    target_profile = None
    for arg in sys.argv[1:]:
        if arg not in ("--check",):
            target_profile = arg

    print(f"{'='*60}")
    print(f"  Auto Context-Length Sync {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")

    cache_lookup = load_cache()
    print(f"\n📦 Models cache loaded: {len(cache_lookup)} entries")
    print()

    profiles = sorted(os.listdir(PROFILES_DIR)) if not target_profile else [target_profile]

    changed = 0
    skipped = 0
    errors = []

    for profile_name in profiles:
        profile_dir = os.path.join(PROFILES_DIR, profile_name)
        if not os.path.isdir(profile_dir):
            continue

        content, config, config_path = read_config(profile_dir)
        if config is None:
            print(f"  ⏭️  {profile_name}: no config.yaml")
            skipped += 1
            continue

        model = config.get("model", {})
        model_name = model.get("default", "")
        provider = model.get("provider", "")

        if not model_name:
            print(f"  ⏭️  {profile_name}: no model.default set")
            skipped += 1
            continue

        ctx, match_info = find_context(profile_name, config, cache_lookup)

        if ctx is None:
            print(f"  ⚠️  {profile_name}: {match_info}")
            errors.append(f"{profile_name}: {match_info}")
            skipped += 1
            continue

        print(f"  🔍 {profile_name:15s} | {model_name:20s} via {provider:15s} → ctx={ctx:>8} ({match_info})")

        if update_context_length(config_path, content, ctx, dry_run=dry_run):
            changed += 1
        else:
            skipped += 1

    print(f"\n{'─'*60}")
    print(f"  Summary: {changed} updated, {skipped} skipped, {len(errors)} errors")
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
