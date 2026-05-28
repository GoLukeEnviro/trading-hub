#!/usr/bin/env python3
"""
heartbeat_intelligence_wrapper.py

Orchestrates the Heartbeat Intelligence Report:
  1. Runs heartbeat_writer.py  (refreshes SQLite)
  2. Runs heartbeat_intelligence.py  (generates Markdown report)
  3. Prints report to stdout (for Agent Prompt Injection)
  4. Sends report via Telegram (optional, graceful fallback)
  5. Spawns an os.fork() watcher that polls for the LLM analysis file
     and sends it via Telegram as well.

Exit code is always 0 — this script never crashes the caller.

Only Python stdlib is used (urllib for Telegram, no curl/wget).
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# OUTPUT_DIR is /opt/data/profiles/orchestrator/cron/output/<job_id>/
# The <job_id> is passed via env var JOB_ID or defaults to "default"
OUTPUT_BASE = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'cron', 'output'))
JOB_ID = os.environ.get('JOB_ID', 'default')
OUTPUT_DIR = os.path.join(OUTPUT_BASE, JOB_ID)

HEARTBEAT_WRITER = os.path.join(SCRIPT_DIR, 'heartbeat_writer.py')
HEARTBEAT_INTELLIGENCE = os.path.join(SCRIPT_DIR, 'heartbeat_intelligence.py')

TELEGRAM_ENV_FILE = '/home/hermes/.config/hermes-freqtrade-heartbeat/telegram_intelligence.env'

# Telegram limits
TG_MAX_LEN = 4096

# Fork-watcher settings
WATCHER_POLL_INTERVAL = 5   # seconds
WATCHER_MAX_WAIT = 180      # seconds


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def load_telegram_env():
    """Load TOKEN and CHAT_ID from the env file. Returns (token, chat_id) or (None, None)."""
    token = None
    chat_id = None
    try:
        if not os.path.isfile(TELEGRAM_ENV_FILE):
            print(f"[wrapper] Telegram env file not found: {TELEGRAM_ENV_FILE}", file=sys.stderr)
            return None, None

        with open(TELEGRAM_ENV_FILE, 'r') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == 'HERMES_INTELLIGENCE_BOT_TOKEN':
                        token = value
                    elif key == 'HERMES_INTELLIGENCE_CHAT_ID':
                        chat_id = value
    except Exception as exc:
        print(f"[wrapper] Failed to read Telegram env: {exc}", file=sys.stderr)

    if not token or not chat_id:
        print("[wrapper] Telegram token or chat_id missing — Telegram disabled", file=sys.stderr)
        return None, None

    return token, chat_id


def telegram_send(token, chat_id, text):
    """Send a Telegram message. Splits into chunks of <= TG_MAX_LEN chars."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Split text into chunks
    chunks = []
    while text:
        if len(text) <= TG_MAX_LEN:
            chunks.append(text)
            break
        # Try to split at a newline to keep formatting intact
        cut = text.rfind('\n', 0, TG_MAX_LEN)
        if cut <= 0:
            cut = TG_MAX_LEN
        chunks.append(text[:cut])
        text = text[cut:]

    for chunk in chunks:
        payload = json.dumps({
            'chat_id': chat_id,
            'text': chunk,
            'parse_mode': 'Markdown',
        }).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                _body = resp.read()
        except Exception as exc:
            print(f"[wrapper] Telegram send failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Step 1 & 2: Run sub-scripts
# ---------------------------------------------------------------------------

def run_script(script_path, label):
    """Run a Python script, capture stdout, and return it. Never raises."""
    if not os.path.isfile(script_path):
        print(f"[wrapper] {label} not found: {script_path}", file=sys.stderr)
        return ''
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"[wrapper] {label} exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        return result.stdout
    except Exception as exc:
        print(f"[wrapper] {label} execution failed: {exc}", file=sys.stderr)
        return ''


# ---------------------------------------------------------------------------
# Step 5: Fork watcher
# ---------------------------------------------------------------------------

def extract_response_section(content):
    """Extract content starting from '## Response' (or '## response') to the end.
    If not found, return the full content."""
    lines = content.split('\n')
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith('## response'):
            start_idx = i
            break
    if start_idx is not None:
        return '\n'.join(lines[start_idx:])
    return content


def watcher_child(output_dir, token, chat_id):
    """
    Runs in a detached child process.
    Polls output_dir for a new .md file, extracts '## Response', sends via Telegram.
    """
    # Detach from parent
    os.setsid()

    # Redirect stdio to /dev/null
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    # Record existing .md files at start so we detect only NEW ones
    existing = set()
    try:
        if os.path.isdir(output_dir):
            for fname in os.listdir(output_dir):
                if fname.endswith('.md'):
                    existing.add(fname)
    except Exception:
        pass

    elapsed = 0
    while elapsed < WATCHER_MAX_WAIT:
        time.sleep(WATCHER_POLL_INTERVAL)
        elapsed += WATCHER_POLL_INTERVAL

        try:
            if not os.path.isdir(output_dir):
                continue

            for fname in os.listdir(output_dir):
                if not fname.endswith('.md'):
                    continue
                if fname in existing:
                    continue

                # New file found — read it
                fpath = os.path.join(output_dir, fname)
                try:
                    with open(fpath, 'r') as fh:
                        content = fh.read()
                except Exception:
                    continue

                if not content.strip():
                    continue

                # Extract the Response section
                response = extract_response_section(content)

                # Send via Telegram
                telegram_send(token, chat_id, response)
                # Done — exit child
                os._exit(0)
        except Exception:
            # Never crash, just keep polling
            pass

    # Timeout — exit silently
    os._exit(0)


def spawn_watcher(output_dir, token, chat_id):
    """Fork a detached watcher child. Returns immediately in the parent."""
    try:
        pid = os.fork()
        if pid == 0:
            # Child — run watcher (never returns)
            watcher_child(output_dir, token, chat_id)
            os._exit(0)
        # Parent — continue
    except Exception as exc:
        print(f"[wrapper] Failed to fork watcher: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Ensure output directory exists
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except Exception as exc:
        print(f"[wrapper] Could not create output dir {OUTPUT_DIR}: {exc}", file=sys.stderr)

    # Step 1: Run heartbeat_writer.py
    print("[wrapper] Step 1: Running heartbeat_writer.py ...", file=sys.stderr)
    run_script(HEARTBEAT_WRITER, 'heartbeat_writer.py')

    # Step 2: Run heartbeat_intelligence.py — capture its stdout as the report
    print("[wrapper] Step 2: Running heartbeat_intelligence.py ...", file=sys.stderr)
    report = run_script(HEARTBEAT_INTELLIGENCE, 'heartbeat_intelligence.py')

    if not report.strip():
        print("[wrapper] No report generated — nothing to send.", file=sys.stderr)
        sys.exit(0)

    # Step 3: Print report to stdout (for Agent Prompt Injection)
    print(report)

    # Also save report to output directory
    try:
        ts = time.strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(OUTPUT_DIR, f'heartbeat_report_{ts}.md')
        with open(report_path, 'w') as fh:
            fh.write(report)
        print(f"[wrapper] Report saved to {report_path}", file=sys.stderr)
    except Exception as exc:
        print(f"[wrapper] Failed to save report: {exc}", file=sys.stderr)

    # Step 4: Send report via Telegram
    token, chat_id = load_telegram_env()
    if token and chat_id:
        print("[wrapper] Step 4: Sending report via Telegram ...", file=sys.stderr)
        try:
            telegram_send(token, chat_id, report)
            print("[wrapper] Telegram report sent.", file=sys.stderr)
        except Exception as exc:
            print(f"[wrapper] Telegram send error: {exc}", file=sys.stderr)

        # Step 5: Spawn fork watcher for LLM analysis file
        print("[wrapper] Step 5: Spawning LLM analysis watcher ...", file=sys.stderr)
        spawn_watcher(OUTPUT_DIR, token, chat_id)
    else:
        print("[wrapper] Step 4 & 5: Telegram disabled (no credentials).", file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f"[wrapper] Unhandled error: {exc}", file=sys.stderr)
    sys.exit(0)
