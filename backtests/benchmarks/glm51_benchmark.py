#!/usr/bin/env python3
"""
GLM-5.1 Custom Benchmark — Trading-Relevant + Standard Reasoning
Runs against Z.AI API (OpenAI-compatible endpoint).

Categories:
1. MATH — Arithmetic, algebra, probability
2. TRADING_REASONING — Signal interpretation, risk assessment, market logic
3. CODE — Python data analysis, signal processing
4. FACTUAL — Financial/trading domain knowledge
5. INSTRUCTION_FOLLOWING — Structured output, format compliance

Usage:
  python3 glm51_benchmark.py [--limit N] [--verbose] [--category CAT]
"""

import json
import urllib.request
import ssl
import time
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# --- Config ---
AUTH_FILE = Path("/home/hermes/.hermes/auth.json")
OUTPUT_DIR = Path("/home/hermes/projects/trading/backtests/benchmarks")
MODEL = "glm-5.1"
MAX_TOKENS = 1500
TEMPERATURE = 0.0
TIMEOUT = 120

# --- Load API credentials ---
def load_api_creds():
    with open(AUTH_FILE) as f:
        d = json.load(f)
    creds = d["credential_pool"]["zai"][0]
    return creds["access_token"], creds["base_url"].rstrip("/")

API_KEY, BASE_URL = load_api_creds()

# --- API call ---
def call_glm(prompt: str, system: str = None, max_retries: int = 2, max_tokens: int = MAX_TOKENS) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )

    for attempt in range(max_retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context())
            data = json.loads(resp.read())
            msg = data["choices"][0]["message"]
            return {
                "content": msg.get("content", ""),
                "reasoning": msg.get("reasoning_content", ""),
                "finish_reason": data["choices"][0].get("finish_reason", ""),
                "usage": data.get("usage", {}),
                "success": True,
            }
        except Exception as e:
            if attempt < max_retries:
                time.sleep(5 * (attempt + 1))
            else:
                return {"content": "", "reasoning": "", "error": str(e), "success": False}

# --- Benchmark Questions ---
BENCHMARKS = {
    "MATH": [
        {
            "id": "math_01",
            "prompt": "Calculate: (15.7 * 23) + (144 / 12) - 8.5. Give only the final number.",
            "expected": "364.6",
            "check": lambda r: "364.6" in r.replace(" ", ""),
        },
        {
            "id": "math_02",
            "prompt": "A coin is flipped 3 times. What is the exact probability of getting exactly 2 heads? Give the fraction.",
            "expected": "3/8",
            "check": lambda r: "3/8" in r or "0.375" in r,
        },
        {
            "id": "math_03",
            "prompt": "If BTC rises 5% from $80,000, then drops 3% from the new price, what is the final price? Round to 2 decimals.",
            "expected": "$81,480.00",
            "check": lambda r: "81,480" in r or "81480" in r.replace(",", ""),
        },
        {
            "id": "math_04",
            "prompt": "Solve for x: 3x - 7 = 2x + 5. Give only x.",
            "expected": "x=12 or just 12",
            "check": lambda r: "12" in r,
        },
        {
            "id": "math_05",
            "prompt": "A trader has a 55% win rate with an average win of $200 and average loss of $150. What is the Expected Value per trade?",
            "expected": "$42.50",
            "check": lambda r: "42.50" in r or "42.5" in r,
        },
    ],
    "TRADING_REASONING": [
        {
            "id": "trade_01",
            "prompt": "RSI is 28, price is touching the lower Bollinger Band, ADX is 14, and volume ratio is 0.8. What strategy fits best and what action would you take? Answer in one sentence.",
            "expected": "Mean reversion BUY (oversold + low volume + low ADX)",
            "check": lambda r: ("mean reversion" in r.lower() or "oversold" in r.lower()) and ("buy" in r.lower() or "long" in r.lower()),
        },
        {
            "id": "trade_02",
            "prompt": "BTC EMA50 is above EMA200, ADX is 32, RSI is 62, and volume is 1.5x average. What is the market regime and recommended bias? One sentence.",
            "expected": "Trending/bullish, long bias",
            "check": lambda r: ("trend" in r.lower() or "bullish" in r.lower()) and ("long" in r.lower() or "buy" in r.lower()),
        },
        {
            "id": "trade_03",
            "prompt": "Your Kelly criterion calculation says to risk 8% of portfolio on a trade. Your risk management rule caps position at 2%. Which do you follow and why? One sentence.",
            "expected": "2% cap (risk management overrides Kelly)",
            "check": lambda r: "2%" in r or "2 percent" in r.lower() or "risk management" in r.lower() or "cap" in r.lower() or "rule" in r.lower(),
        },
        {
            "id": "trade_04",
            "prompt": "A signal has confidence 0.45. Your threshold for ACCEPTED is 0.52. What verdict should the signal get and why? One sentence.",
            "expected": "WATCH_ONLY (below threshold)",
            "check": lambda r: ("watch" in r.lower() or "reject" in r.lower() or "hold" in r.lower()) and ("threshold" in r.lower() or "below" in r.lower() or "0.45" in r or "0.52" in r),
        },
        {
            "id": "trade_05",
            "prompt": "The baseline deterministic model says BUY with confidence 0.65. The LLM says SELL with confidence 0.75. Using a veto model, what is the final signal? One sentence.",
            "expected": "WATCH (LLM veto at >= 0.70 confidence opposing)",
            "check": lambda r: ("watch" in r.lower() or "hold" in r.lower()) and ("veto" in r.lower() or "oppos" in r.lower() or "disagree" in r.lower() or "0.75" in r or "cancel" in r.lower()),
        },
        {
            "id": "trade_06",
            "prompt": "SOL just broke below its 200-day EMA on high volume. ADX is 38. What does this most likely signal? One sentence.",
            "expected": "Bearish breakdown / trend reversal / short bias",
            "check": lambda r: ("bearish" in r.lower() or "breakdown" in r.lower() or "short" in r.lower() or "sell" in r.lower() or "down" in r.lower()) and ("ema" in r.lower() or "200" in r or "trend" in r.lower()),
        },
    ],
    "CODE": [
        {
            "id": "code_01",
            "prompt": "Write a Python function called `calculate_rsi(prices, period=14)` that computes the RSI from a list of prices. Use Wilder's smoothing method. Output the complete function code between ```python and ``` markers.",
            "expected": "Working RSI function",
            "check": lambda r: "def calculate_rsi" in r and ("gain" in r.lower() or "avg_gain" in r.lower()) and ("loss" in r.lower() or "avg_loss" in r.lower()) and "period" in r,
            "max_tokens": 3000,
        },
        {
            "id": "code_02",
            "prompt": "Write a Python one-liner that filters a list of dicts `trades` to only closed trades with profit_pct > 0. Return only the one-liner.",
            "expected": "[t for t in trades if t.get('profit_pct', 0) > 0 and t.get('is_open') == False]",
            "check": lambda r: "trades" in r and "profit" in r.lower() and "for" in r and (">" in r or "0" in r),
        },
        {
            "id": "code_03",
            "prompt": "Write a Python function `kelly_fraction(p, b)` that returns the Kelly criterion fraction f = (p*b - (1-p)) / b. Include a guard for b <= 0 returning 0.0. Only the function, no explanation.",
            "expected": "Working Kelly function with guard",
            "check": lambda r: "def kelly" in r.lower() and "p" in r and "b" in r and ("<=" in r or "b <=" in r or "b ==" in r) and "0.0" in r,
        },
    ],
    "FACTUAL": [
        {
            "id": "fact_01",
            "prompt": "What does RSI measure in technical analysis? Answer in exactly one sentence.",
            "expected": "Momentum/speed of price changes (0-100 oscillator)",
            "check": lambda r: ("momentum" in r.lower() or "speed" in r.lower() or "strength" in r.lower()) and ("price" in r.lower() or "change" in r.lower() or "overbought" in r.lower() or "oversold" in r.lower()),
        },
        {
            "id": "fact_02",
            "prompt": "What is the standard interpretation when the 50-day EMA crosses above the 200-day EMA? One sentence.",
            "expected": "Golden cross / bullish signal",
            "check": lambda r: ("golden cross" in r.lower() or "bullish" in r.lower() or "buy" in r.lower()),
        },
        {
            "id": "fact_03",
            "prompt": "In the context of algorithmic trading, what is 'slippage'? One sentence.",
            "expected": "Difference between expected and actual execution price",
            "check": lambda r: ("differ" in r.lower() or "gap" in r.lower() or "between" in r.lower()) and ("expect" in r.lower() or "intend" in r.lower() or "planned" in r.lower()) and ("price" in r.lower() or "execut" in r.lower()),
        },
        {
            "id": "fact_04",
            "prompt": "What does ADX measure and what value indicates a strong trend? One sentence.",
            "expected": "Trend strength (not direction), >25 indicates strong trend",
            "check": lambda r: ("trend" in r.lower() and ("strength" in r.lower() or "intensity" in r.lower() or "strong" in r.lower())) and ("25" in r or "20" in r),
        },
    ],
    "INSTRUCTION_FOLLOWING": [
        {
            "id": "instr_01",
            "prompt": 'Return a JSON object with exactly these keys: {"signal": "BUY", "confidence": 0.72, "pair": "BTC/USDT"}. Return ONLY the JSON, nothing else.',
            "expected": "Valid JSON with signal, confidence, pair",
            "check": lambda r: '"signal"' in r and '"BUY"' in r and '"confidence"' in r and "0.72" in r and '"pair"' in r and '"BTC/USDT"' in r,
        },
        {
            "id": "instr_02",
            "prompt": "List exactly 3 risks of using leverage in crypto trading. Number them 1-3. No other text.",
            "expected": "3 numbered risks",
            "check": lambda r: ("1." in r or "1)" in r) and ("2." in r or "2)" in r) and ("3." in r or "3)" in r),
        },
        {
            "id": "instr_03",
            "prompt": "Respond with only the word 'PASS'. No other text, no punctuation, no explanation.",
            "expected": "PASS",
            "check": lambda r: r.strip().upper() == "PASS",
        },
    ],
}

def run_benchmark(category: str = None, limit: int = None, verbose: bool = False):
    """Run benchmark questions and collect results."""
    results = {}
    total_correct = 0
    total_questions = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_time = 0

    categories = [category] if category else list(BENCHMARKS.keys())

    for cat in categories:
        questions = BENCHMARKS[cat]
        if limit:
            questions = questions[:limit]

        cat_results = []
        cat_correct = 0

        for q in questions:
            start = time.time()
            mt = q.get("max_tokens", MAX_TOKENS)
            response = call_glm(q["prompt"], max_tokens=mt)
            elapsed = time.time() - start

            content = response.get("content", "")
            passed = q["check"](content) if response["success"] else False

            usage = response.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_time += elapsed

            result = {
                "id": q["id"],
                "category": cat,
                "prompt": q["prompt"],
                "expected": q["expected"],
                "response": content[:500],
                "reasoning_length": len(response.get("reasoning", "")),
                "passed": passed,
                "latency_s": round(elapsed, 1),
                "tokens": usage,
                "error": response.get("error"),
            }
            cat_results.append(result)

            if passed:
                cat_correct += 1
                total_correct += 1
            total_questions += 1

            status = "PASS" if passed else "FAIL"
            if verbose:
                print(f"  [{status}] {q['id']} ({elapsed:.1f}s) — {content[:80]}")
            else:
                print(f"  [{status}] {q['id']} ({elapsed:.1f}s)")

            time.sleep(1)  # Rate limit courtesy

        results[cat] = {
            "questions": len(questions),
            "correct": cat_correct,
            "score": f"{cat_correct}/{len(questions)}",
            "accuracy": round(cat_correct / len(questions) * 100, 1) if questions else 0,
            "details": cat_results,
        }

    # Summary
    summary = {
        "model": MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_questions": total_questions,
        "total_correct": total_correct,
        "overall_accuracy": round(total_correct / total_questions * 100, 1) if total_questions else 0,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_latency_s": round(total_time, 1),
        "avg_latency_s": round(total_time / total_questions, 1) if total_questions else 0,
        "categories": {cat: {"score": results[cat]["score"], "accuracy": results[cat]["accuracy"]} for cat in results},
    }

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = OUTPUT_DIR / f"glm51_benchmark_{ts}.json"
    out_file.write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False))

    return summary, out_file


def print_report(summary: dict):
    """Print a clean benchmark report."""
    print("\n" + "=" * 60)
    print(f"  GLM-5.1 BENCHMARK REPORT")
    print(f"  {summary['timestamp'][:19]}")
    print("=" * 60)
    print()
    print(f"  Overall: {summary['total_correct']}/{summary['total_questions']} ({summary['overall_accuracy']}%)")
    print(f"  Tokens:  {summary['total_prompt_tokens']} prompt + {summary['total_completion_tokens']} completion")
    print(f"  Latency: {summary['total_latency_s']}s total, {summary['avg_latency_s']}s avg")
    print()
    print(f"  {'Category':<25s} {'Score':<10s} {'Accuracy'}")
    print(f"  {'-'*25} {'-'*10} {'-'*10}")
    for cat, info in summary["categories"].items():
        print(f"  {cat:<25s} {info['score']:<10s} {info['accuracy']}%")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GLM-5.1 Custom Benchmark")
    parser.add_argument("--category", choices=list(BENCHMARKS.keys()), help="Run only one category")
    parser.add_argument("--limit", type=int, help="Limit questions per category")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show responses")
    args = parser.parse_args()

    print(f"GLM-5.1 Benchmark — Model: {MODEL}, Max Tokens: {MAX_TOKENS}, Temp: {TEMPERATURE}")
    if args.category:
        print(f"Category: {args.category}")
    print()

    summary, out_file = run_benchmark(
        category=args.category,
        limit=args.limit,
        verbose=args.verbose,
    )

    print_report(summary)
    print(f"\nFull results: {out_file}")
