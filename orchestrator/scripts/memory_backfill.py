#!/usr/bin/env python3
"""Memory Backfill — Extract facts from recent sessions into local Mem0 stack.

Runs as a Hermes cron job (no_agent=true) every 6 hours.
Scans sessions from the last N hours, extracts durable facts from user messages,
deduplicates against existing memories, and stores new facts via the Mem0 REST API.

Usage:
    python3 memory_backfill.py [--since HOURS] [--dry-run] [--verbose]

Options:
    --since HOURS   Look-back window in hours (default: 48, range: 24-72)
    --dry-run       Extract and classify but do NOT store to Mem0
    --verbose       Print detailed per-message analysis to stdout

Exit codes:
    0 = success (including "nothing to do")
    1 = partial failure (some facts stored, some errors)
    2 = total failure (could not connect to API or DB)

Output: single-line summary on stdout (consumed by Hermes cron scheduler).
        Detailed log written to LOG_FILE.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("MEM0_BASE_URL", "http://green-mem0:8787")
DB_PATH = "/opt/data/state.db"
LOG_FILE = Path("/opt/data/profiles/orchestrator/logs/memory-backfill.log")
LOCK_FILE = Path("/tmp/memory-backfill.lock")
USER_ID = "luke-hermes"
AGENT_ID = "hermes"

# Fact extraction keywords per category
CATEGORY_KEYWORDS = {
    "user_preference": [
        "ich will", "bevorzug", "immer", "ab sofort", "ab heute", "nicht mehr",
        "will ich", "hasse", "mag ich", "nervt", "finde ich", "bevorzuge",
        "i prefer", "always", "never", "from now",
    ],
    "decision": [
        "ok für", "genehmigt", "abgelehnt", "decommission", "stoppen", "kill",
        "entschied", "beschlossen", "freigabe", "grünes licht", "approved",
        "reject", "cancel", "deploy", "go live",
    ],
    "architecture": [
        "endpoint", "config", "pfad", "pfade", "docker", "container",
        "netzwerk", "port", "volume", "bind mount", "env", "api",
        "stack", "backend", "frontend", "service", "pipeline",
    ],
    "correction": [
        "mein fehler", "falsch", "nein eigentlich", "stimmt nicht",
        "korrektur", "vergiss", "ignorier", "my mistake", "wrong",
        "actually", "no wait", "correction",
    ],
    "completed_task": [
        "erledigt", "gebaut", "deployed", "fertig", "abgeschlossen",
        "implementiert", "erstellt", "angelegt", "done", "completed",
        "built", "shipped",
    ],
    "technical_fact": [
        "threshold", "stoploss", "parameter", "modell", "embedding",
        "freqai", "xgboost", "backtest", "strategy", "signal",
        "stop-loss", "take-profit", "risk-reward", "profit factor",
    ],
}

# Messages to skip (noise patterns)
SKIP_PATTERNS = [
    "<agent_prompt>",
    "<agent_task>",
    "<agent_rules",
    "[IMPORTANT: Background process",
    "[IMPORTANT: The user has invoked",
    "[Your active task list was preserved",
    "[Note: model was just switched",
    "[CONTEXT COMPACTION",
    "[CONTEXT COMPACTION — REFERENCE ONLY",
    "[System note:",
    "[The user sent a voice message",
    "[Note:",
]

# Substring patterns that indicate non-factual content (checked anywhere in msg)
SKIP_CONTAINS = [
    "Extract ALL memory-worthy facts from",
    "delegate_task",
    "subagent",
    "Goal: Extract",
    "DB: /opt/data/state.db",
    "SESSION_IDS =",
    "Tool call:",
    "Tool result:",
    "Prompt für Hermes:",
    "Hier ist der fertige, direkte Agenten-Prompt",
    "Bashpython3",
    "Pythonimport json",
    # Persona assignments (catch bold-markdown and plain variants)
    "Senior Autonomous Trading Systems Auditor",
    "Senior Automation Engineer",
    "Senior Automation Architect",
    "Senior Trading Systems Auditor",
    "ehrlicher Senior",
    "extrem ehrlicher",
    "extrem pragmatischer",
    "pragmatischer, extrem ehrlicher",
    # Cron table dumps / job listings
    "Ghost-Detection + Auto-Hea",
    "ghostbuster     |",
    "| alle ",
    "| no_agent |",
    # System/operational noise
    "intentional_runtime_override",
    "clarify timed out",
    "Custom personalities can be defined in config.yaml",
    # Pasted text blocks
    "Pasted text #",
    "lines → /opt/data/profiles/orchestrator/pastes/",
]


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging to both file and stderr."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("memory-backfill")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # File handler (always detailed) — with PermissionError fallback
    try:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    except PermissionError:
        # Fallback to stderr if log file is not writable (e.g. root-owned)
        import warnings
        warnings.warn(f"Cannot write to {LOG_FILE}, using stderr only", stacklevel=2)

    # Stderr handler (for verbose mode)
    if verbose:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG)
        sh.setFormatter(logging.Formatter("%(levelname)-5s %(message)s"))
        logger.addHandler(sh)

    return logger


# ---------------------------------------------------------------------------
# Mem0 REST API helpers
# ---------------------------------------------------------------------------

def api_health_check() -> bool:
    """Check if Mem0 API is reachable."""
    try:
        req = Request(f"{API_BASE}/health")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def api_get_all_memories() -> Tuple[List[Dict], Optional[str]]:
    """Fetch all existing memories. Returns (memories_list, error_msg)."""
    try:
        req = Request(f"{API_BASE}/memories/all?user_id={USER_ID}")
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        # Unwrap: {"status":"ok","result":{"results":[...]}}
        if isinstance(data, dict):
            result = data.get("result", data)
            if isinstance(result, dict):
                return result.get("results", []), None
            if isinstance(result, list):
                return result, None
        return [], None
    except Exception as e:
        return [], str(e)


def text_optimize_for_storage(fact: str) -> str:
    """Optimize fact text for better embedding search before storing.

    Goal: Mem0's internal LLM reformats memories into 'User [action]' prose.
    By pre-optimizing the text structure, we reduce reformatting and
    preserve keyword density for better vector search.

    Strategy:
    1. Remove 'User ' / 'User's ' / 'The user ' prefix if present (Mem0 adds its own)
    2. Promote technical keywords to front (versions, paths, params, methods)
    3. Keep it factual and terse — let keywords drive the embedding
    """
    import re as _re

    text = fact.strip()

    # Remove existing "User" / "The user" / "User's" prefixes (Mem0 adds its own)
    text = _re.sub(r"^(?:User|The user|User's|Users)\s+", "", text, flags=_re.IGNORECASE)

    # Remove "Luke" / "Luke's" prefixes (redundant — everything is luke-hermes)
    text = _re.sub(r"^Luke(?:'s)?\s+", "", text, flags=_re.IGNORECASE)

    # Remove "Assistant" / "The assistant" prefixes
    text = _re.sub(r"^(?:The\s+)?Assistant\s+", "", text, flags=_re.IGNORECASE)

    # Convert passive reported-speech to active factual statements
    # "User noted that X was deployed" → "X deployed"
    reported = _re.match(
        r"(?:mentions?|notes?|states?|reports?|indicates?|says?|thinks?)\s+that\s+",
        text, _re.IGNORECASE
    )
    if reported:
        text = text[reported.end():]

    # Convert "prefers/requires/wants/mandates/instructs that" → chop "that"
    text = _re.sub(r"\b(prefers|requires|wants|mandates|instructs|requests)\s+that\s+",
                   "", text, flags=_re.IGNORECASE)

    # Capitalize first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Remove "to" / "in order to" before the core action
    # e.g., "User wants to set X" → after prefix removal → "wants to set X" → "Set X"
    if text.lower().startswith(("wants to ", "needs to ", "likes to ", "prefers to ")):
        verb = text.split()[2]  # "wants to set" → "set"
        rest = " ".join(text.split()[3:])
        if verb and rest:
            text = verb.capitalize() + " " + rest

    # Ensure minimum content length
    if len(text) < 15:
        return fact  # Return original if optimization broke it

    return text


def api_store_fact(fact: str) -> Tuple[bool, Optional[str]]:
    """Store a single fact via text format. Text is optimized before storage."""
    try:
        optimized = text_optimize_for_storage(fact)
        payload = json.dumps({
            "text": optimized,
            "user_id": USER_ID,
            "agent_id": AGENT_ID,
        }).encode("utf-8")
        req = Request(f"{API_BASE}/memories/add", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=30) as resp:
            resp.read()
        return True, None
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)


def build_dedup_set(memories: List[Dict]) -> Set[str]:
    """Build dedup set from existing memories (first-60-char lowercase prefix)."""
    prefixes = set()
    for m in memories:
        content = m.get("memory", "").strip().lower()[:60]
        if content:
            prefixes.add(content)
    return prefixes


# ---------------------------------------------------------------------------
# Session DB helpers
# ---------------------------------------------------------------------------

def get_sessions(since_hours: int) -> List[Dict]:
    """Get non-cron sessions from the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    cutoff_ts = cutoff.timestamp()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, title, source, started_at, message_count, model
        FROM sessions
        WHERE started_at >= ?
          AND source != 'cron'
          AND message_count >= 5
        ORDER BY started_at ASC
    """, (cutoff_ts,)).fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "title": r["title"] or "N/A",
            "started": datetime.fromtimestamp(r["started_at"], tz=timezone.utc)
                         .strftime("%Y-%m-%d %H:%M"),
            "msgs": r["message_count"],
            "model": r["model"] or "?",
            "source": r["source"],
        }
        for r in rows
    ]


def get_user_messages(session_id: str) -> List[str]:
    """Get filtered user messages from a session."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT content FROM messages
        WHERE session_id = ? AND role = 'user'
        ORDER BY timestamp
    """, (session_id,)).fetchall()
    conn.close()

    messages = []
    for (content,) in rows:
        text = content.strip()
        if len(text) < 20:
            continue
        # Skip noise patterns (prefix match)
        if any(text.startswith(p) for p in SKIP_PATTERNS):
            continue
        # Skip noise patterns (substring match)
        if any(s in text for s in SKIP_CONTAINS):
            continue
        # Skip very short system-like messages
        if text.startswith("/") and len(text) < 20:
            continue
        # Skip role/prompt assignments that are pure persona definitions
        if text.lower().startswith("du bist ") and len(text) < 50:
            continue
        messages.append(text)

    return messages


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------

def classify_message(msg: str) -> Optional[str]:
    """Classify a user message into a fact category, or None if not a fact."""
    msg_lower = msg.lower()

    # Score each category by keyword match count
    scores: Dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        # No keywords matched — check for general substance
        # Messages longer than 100 chars with specific paths/numbers are likely facts
        has_path = "/" in msg and len(msg) > 60
        has_number = any(c.isdigit() for c in msg) and len(msg) > 50
        has_technical = any(
            kw in msg_lower
            for kw in ["freqtrade", "freqforge", "rebel", "regime", "mem0",
                        "docker", "signal", "strategy", "config", "backtest"]
        )
        if (has_path or has_number) and has_technical:
            return "technical_fact"
        return None

    # Return highest-scoring category
    return max(scores, key=scores.get)


def extract_fact_from_message(msg: str, session_title: str) -> Optional[str]:
    """Extract a single concise fact from a user message.

    For simple messages, use the message itself (truncated).
    For complex messages, extract the core actionable statement.
    """
    # Clean up the message
    text = msg.strip()

    # Remove common boilerplate prefixes
    for prefix in ["Du bist mein ", "Du bist ein ", "Prompt für Hermes:"]:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    # Strip "Hermes, [Role – ]Title" persona prefixes (handles task-assignment headers)
    import re as _re
    hermes_prefix_match = _re.match(
        r"^(?:\[?Note:.*?\]?\s*\n*\s*)?"
        r"Hermes,\s+"
        r"(?:neuer\s+)?"
        r"(?:Auftrag|Dauerauftrag|Update\s+)?"
        r".+?(?:Agent|Architect|Master|Auditor|Engineer|Mode)\s*"
        r"(?:–|-|:)\s*",
        text, _re.IGNORECASE | _re.DOTALL
    )
    if hermes_prefix_match:
        text = text[hermes_prefix_match.end():].strip()
        # If after stripping we got a bare role continuation, skip it
        if len(text) < 20 or text.lower().startswith("du bist "):
            return None

    # Also strip simple "Hermes, [Role]:" prefix without dash
    simple_hermes = _re.match(
        r"^Hermes,\s+.+?(?:Agent|Architect|Master|Auditor|Optimizer)\s*:\s*",
        text, _re.IGNORECASE
    )
    if simple_hermes and len(text) > simple_hermes.end():
        text = text[simple_hermes.end():].strip()

    # Remove "[Note: model was just switched from ... ]" prefix that survived filter
    note_model_prefix = _re.match(r"^\[Note:\s*model was just switched.*?\]\s*\n*\s*", text)
    if note_model_prefix:
        text = text[note_model_prefix.end():].strip()
        # Re-check persona stripping after removing model note
        hermes_prefix_after_note = _re.match(
            r"^Hermes,\s+.+?(?:Agent|Architect|Master|Auditor|Optimizer)\s*(?:–|-|:)\s*",
            text, _re.IGNORECASE
        )
        if hermes_prefix_after_note:
            text = text[hermes_prefix_after_note.end():].strip()
            if len(text) < 20 or text.lower().startswith("du bist "):
                return None

    if text.strip().startswith(("##", "---", "[19.", "[20.")):
        return None
    # Skip acknowledgements / copied assistant-style text that contains no user fact.
    normalized_start = text.lstrip("#*-_` >")
    # Strip leading numbered list markers like "4. ", "1. "
    import re as _re
    normalized_no_num = _re.sub(r"^\d+\.\s+", "", normalized_start)
    ack_prefixes = ["✅ Verstanden", "Verstanden.", "Alles klar", "Fertig."]
    assistant_style_prefixes = [
        "Ja —", "Ja -", "Ja,", "Nein,", "Ehrliche Lagebeschreibung",
        "Phase", "1. Paper", "Mit den jetzt aktiven", "4/8", "3\n",
        "dream-mode", "Dream Mode", "neu start", "neustart", "Finale Code",
        "Dann hatten wir noch", "Telegram-Alert Test", "erst backup",
        "Fallback-Verhalten",
    ]
    if any(normalized_start.startswith(p) for p in ack_prefixes + assistant_style_prefixes):
        return None
    if any(normalized_no_num.startswith(p) for p in assistant_style_prefixes):
        return None

    # Skip if it starts with a role assignment
    if text.lower().startswith("du bist "):
        return None
    # Skip mode assignments ("Du bleibst im...", "Du bleibst auf...")
    if text.lower().startswith("du bleibst "):
        return None

    # Skip system prompts
    if text.startswith("<prompt>") or text.startswith("<agent_prompt>"):
        return None
    if text.startswith("<agent_"):
        return None

    # Skip task assignments that are purely operational
    operational_prefixes = [
        "SYSTEM:", "TASK:", "MODE:", "ZIEL:",
        "Check mal bitte", "Checke mal bitte",
        "Prüf mal bitte", "Guck mal",
        "Führe bitte einen", "Führe den Test", "Führe einen", "Führe jetzt",
        "Kannst du bitte mal", "Erstelle das Script", "Erstelle bitte",
        "Erweitere die", "Ersetze die", "Behebe", "Repariere",
        "Kopiere den", "Kopiere die", "Gib diesen Prompt",
        "Nimm die api", "nimm die api", "Starte jetzt", "Nach dem Lauf",
        "1. Stage", "# 1.", "Bash", "Python",
        # English operational task patterns
        "Gather a comprehensive", "Gather comprehensive",
        "Emergency repair:", "Emergency cleanup:",
        "Check the ", "Check all ", "Check if ",
        "Bucket-Tabelle",
        "erstelle zuerst",
        # Vague task headers (no specific facts)
        "Sofort-Fix", "Sofort-Aktion", "Finaler Fix-Run",
        "Abschluss der letzten", "Git Housekeeping",
        "Cronjob Response:", "Rest-Probleme final",
        "Tiefenanalyse der zwei",
        # Role/mode assignments
        "Ab sofort hast du die Rolle",
        "Ab sofort übernimmst du die Rolle",
        "Ab sofort läuft das gesamte",
        "Ab sofort läuft der gesamte",
        "Ab sofort baust du in alle",
    ]
    if any(text.startswith(p) for p in operational_prefixes):
        return None

    # Also check after stripping leading markdown bold (**)
    text_stripped = text.lstrip("*").lstrip()
    if any(text_stripped.startswith(p) for p in operational_prefixes):
        return None

    # Skip pure prompt assignments (e.g. "Senior Quant Developer...")
    persona_starts = [
        "Senior Quant", "Senior Freqtrade", "Senior Trading",
        "Du bist im HIGH-MODE", "Du bist Grok",
        "Senior Autonomous", "Senior Automation",
        "Principal System", "Principal Report",
        "Full Autonomous", "Full Autonomous Cleanup",
        "Report Auditor", "Report Architect",
    ]
    if any(text.startswith(p) for p in persona_starts):
        return None
    if any(text_stripped.startswith(p) for p in persona_starts):
        return None

    # Skip pure questions with no embedded facts (end with ?? and <60 chars)
    if text.rstrip().endswith("??") and len(text) < 60:
        return None

    # Skip timestamped log lines like [22.05.2026 03:00]
    import re as _re
    if _re.match(r"^\[\d{2}\.\d{2}\.\d{4}\s", text):
        return None

    # Skip task-assignment headers: "Hermes, [Role] – [Title]"
    if _re.match(r"^Hermes,\s+.+\s[–\-]\s+", text):
        return None
    # Also after markdown bold stripping
    if _re.match(r"^Hermes,\s+.+\s[–\-]\s+", text_stripped):
        return None

    # Skip task delegation prompts
    if "delegate_task" in text or "subagent" in text.lower():
        return None

    # Truncate at first newline for multi-line messages (keep the core statement)
    # But skip header-only first lines (e.g. "Sofort-Fix:") — use the second line if it's meatier
    lines = text.split("\n")
    if len(lines) > 1 and len(lines[0].strip()) > 20:
        first_line = lines[0].strip()
        # If first line is a short header ending with : or !, prefer subsequent lines
        if first_line.rstrip().endswith((":", "!", "?")) and len(first_line) < 80:
            # Look for the first line with substantial content
            for l in lines[1:]:
                stripped = l.strip()
                if len(stripped) > 30 and not stripped.startswith(("#", "-", "**")):
                    text = stripped
                    break
            else:
                text = first_line
        else:
            text = first_line

    # Truncate to reasonable length
    if len(text) > 300:
        text = text[:297] + "..."

    # Skip if still too short or generic
    if len(text) < 25:
        return None

    # Check for generic status requests
    generic_requests = [
        "wie laufen die", "verschaffe mir", "gib mir einen überblick",
        "was ist der status", "how are the", "give me an overview",
        "check mal bitte ganz genau", "vor ausführung bitte", "aktuelle aufgabe:",
    ]
    if any(g in text.lower() for g in generic_requests) and len(text) < 200:
        return None

    # Skip if the message is purely a question with no embedded facts
    question_only = [
        "über welchen benutzter läuft",
        "was ist das",
        "wo ist",
    ]
    if any(text.lower().startswith(q) for q in question_only):
        return None

    # Skip pure imperative task assignments (start with command verbs and < 80 chars)
    command_verbs = [
        "extrahiere ", "führe ", "mache ", "starte ", "behebe ",
        "prüfe ", "checke ", "erstelle ", "erweitere ", "ersetze ",
        "kopiere ", "gib ", "nimm ", "lösche ", "entferne ", "aktualisiere ",
        "aktiviere ", "deaktiviere ", "setze ", "lege ", "schreibe ",
        "verschaffe ", "verificiere ", "validierte ", "guck ",
    ]
    text_lower = text.lower()
    if any(text_lower.startswith(v) for v in command_verbs) and len(text) < 120:
        return None

    # Skip if text is purely a task header with no specific detail
    # (single sentence, < 100 chars, ends with : or !, no specific path/number)
    has_specific = "/" in text or any(c.isdigit() for c in text if c.isdigit())
    if (text.rstrip().endswith((":", "!")) and len(text) < 100 
        and not has_specific):
        return None

    # Skip version-stamped task headers like "Task Name (v4.5)" or "Topic (v4.5 – Detail)"
    if _re.search(r"\(v\d+\.\d+.*?\)", text) and len(text) < 100:
        return None

    # Skip role-assignment messages (definition of a role, not a fact)
    # e.g. "Ab sofort hast du die Rolle X"
    role_assignment = _re.search(
        r"(?:Rolle\s+.+?(?:Agent|Architect|Master|Mode))|"
        r"(?:bist\s+(?:ab\s+sofort|jetzt)\s+.+?(?:Architect|Master|Manager|Agent))",
        text, _re.IGNORECASE
    )
    if role_assignment and len(text) < 90:
        return None

    # Skip "Du" directives targeting the agent with no embedded fact
    # (e.g. "Du bist jetzt…" already caught above, but also "Du bleibst auf Mode X")
    du_directive = _re.match(
        r"^Du\s+(bist|bleibst|hast|wirst|arbeitest)",
        text, _re.IGNORECASE
    )
    if du_directive and len(text) < 80:
        return None

    # Skip short "Hermes, do X" directives (not task assignments with specifics)
    if text.startswith("Hermes,") and len(text) < 100:
        return None

    return text


# ---------------------------------------------------------------------------
# Main backfill logic
# ---------------------------------------------------------------------------

def run_backfill(since_hours: int, dry_run: bool, verbose: bool) -> Dict[str, Any]:
    """Run the memory backfill process. Returns stats dict."""

    log = setup_logging(verbose)
    stats = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "since_hours": since_hours,
        "sessions_scanned": 0,
        "messages_scanned": 0,
        "facts_extracted": 0,
        "facts_deduped": 0,
        "facts_stored": 0,
        "facts_failed": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    log.info("=" * 60)
    log.info("Memory Backfill starting (since=%dh, dry_run=%s)", since_hours, dry_run)

    # Step 1: Health check
    if not api_health_check():
        msg = f"Mem0 API unreachable at {API_BASE}"
        log.error(msg)
        stats["errors"].append(msg)
        return stats

    log.info("API health check: OK (%s)", API_BASE)

    # Step 2: Get existing memories for dedup
    existing, err = api_get_all_memories()
    if err:
        log.warning("Could not fetch existing memories: %s — proceeding without dedup", err)
        dedup_set = set()
        stats["existing_count"] = 0
    else:
        dedup_set = build_dedup_set(existing)
        stats["existing_count"] = len(existing)
        log.info("Existing memories: %d (dedup set: %d prefixes)", len(existing), len(dedup_set))

    # Step 3: Get sessions
    sessions = get_sessions(since_hours)
    stats["sessions_scanned"] = len(sessions)
    log.info("Sessions found: %d", len(sessions))

    if not sessions:
        log.info("No sessions to process. Done.")
        stats["finished_at"] = datetime.now(timezone.utc).isoformat()
        return stats

    # Step 4: Extract facts from each session
    all_facts: List[Tuple[str, str, str]] = []  # (fact, category, session_id)

    for session in sessions:
        sid = session["id"]
        title = session["title"]
        log.info("Processing session %s (%s, %d msgs) — %s",
                 sid[:20], session["started"], session["msgs"], title[:40])

        messages = get_user_messages(sid)
        stats["messages_scanned"] += len(messages)

        for msg in messages:
            category = classify_message(msg)
            if category is None:
                continue

            fact = extract_fact_from_message(msg, title)
            if fact is None:
                continue

            all_facts.append((fact, category, sid))
            log.debug("  [%s] %s", category, fact[:80])

    stats["facts_extracted"] = len(all_facts)
    log.info("Total facts extracted: %d", len(all_facts))

    # Step 5: Dedup and store
    new_facts = []
    for fact, category, sid in all_facts:
        prefix = fact.strip().lower()[:60]
        if prefix in dedup_set:
            stats["facts_deduped"] += 1
            log.debug("  DEDUP: %s", fact[:60])
            continue
        new_facts.append((fact, category, sid))
        dedup_set.add(prefix)  # Prevent intra-run duplicates

    log.info("New facts (after dedup): %d (deduped: %d)",
             len(new_facts), stats["facts_deduped"])

    if dry_run:
        log.info("DRY RUN — not storing %d facts", len(new_facts))
        for fact, category, sid in new_facts:
            log.info("  [DRY] [%s] %s", category, fact[:80])
    else:
        for fact, category, sid in new_facts:
            success, error = api_store_fact(fact)
            if success:
                stats["facts_stored"] += 1
                log.info("  STORED [%s] %s", category, fact[:70])
            else:
                stats["facts_failed"] += 1
                log.warning("  FAILED [%s] %s — %s", category, fact[:50], error)
                stats["errors"].append(f"Store failed: {error}")

    stats["finished_at"] = datetime.now(timezone.utc).isoformat()

    # Summary
    summary = (
        f"Memory Backfill: {stats['sessions_scanned']} sessions, "
        f"{stats['messages_scanned']} msgs scanned, "
        f"{stats['facts_extracted']} extracted, "
        f"{stats['facts_deduped']} deduped, "
        f"{stats['facts_stored']} stored, "
        f"{stats['facts_failed']} failed"
        + (" (DRY RUN)" if dry_run else "")
    )
    log.info("SUMMARY: %s", summary)

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Memory Backfill Cron Job")
    parser.add_argument("--since", type=int, default=48,
                        help="Look-back window in hours (default: 48, range: 24-72)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract and classify but do NOT store")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed per-message analysis")
    args = parser.parse_args()

    # Clamp since to valid range
    since_hours = max(24, min(72, args.since))

    # Run
    stats = run_backfill(since_hours, args.dry_run, args.verbose)

    # Print one-line summary to stdout (consumed by Hermes scheduler)
    parts = [
        f"Memory Backfill: {stats['sessions_scanned']} sessions",
        f"{stats['messages_scanned']} msgs",
        f"{stats['facts_extracted']} extracted",
        f"{stats['facts_deduped']} deduped",
        f"{stats['facts_stored']} stored",
    ]
    if stats["facts_failed"] > 0:
        parts.append(f"{stats['facts_failed']} FAILED")
    if stats["dry_run"]:
        parts.append("DRY RUN")
    print(" | ".join(parts))

    # Exit code
    if stats["facts_failed"] > 0 and stats["facts_stored"] == 0:
        sys.exit(2)  # Total failure
    elif stats["facts_failed"] > 0:
        sys.exit(1)  # Partial failure
    sys.exit(0)


if __name__ == "__main__":
    main()
