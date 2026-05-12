#!/usr/bin/env python3
"""
Multi-Model Benchmark Comparison
Compares API models on trading-relevant tasks against the Z.AI GLM-5.1 baseline.
"""
import json, urllib.request, ssl, time, sys
from pathlib import Path
from datetime import datetime, timezone

AUTH_FILE = Path("/home/hermes/.hermes/auth.json")
OUTPUT_DIR = Path("/home/hermes/projects/trading/backtests/benchmarks")
MAX_TOKENS = 1500
TEMPERATURE = 0.0
TIMEOUT = 120

def load_api_creds(provider: str):
    with open(AUTH_FILE) as f:
        d = json.load(f)
    creds = d["credential_pool"][provider][0]
    return creds["access_token"], creds["base_url"].rstrip("/")

def call_model(base_url: str, key: str, model: str, prompt: str, max_tokens=1500) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context())
        data = json.loads(resp.read())
        msg = data["choices"][0]["message"]
        return {
            "content": msg.get("content", ""),
            "reasoning": msg.get("reasoning_content", ""),
            "usage": data.get("usage", {}),
            "success": True,
        }
    except Exception as e:
        return {"content": "", "reasoning": "", "error": str(e), "success": False}

# All benchmark questions
BENCHMARKS = {
    "MATH": [
        {"id": "math_01", "prompt": "Calculate: (15.7 * 23) + (144 / 12) - 8.5. Give only the final number.", "check": lambda r: "364.6" in r.replace(" ", "")},
        {"id": "math_02", "prompt": "A coin is flipped 3 times. What is the exact probability of getting exactly 2 heads? Give the fraction.", "check": lambda r: "3/8" in r or "0.375" in r},
        {"id": "math_03", "prompt": "If BTC rises 5% from $80,000, then drops 3% from the new price, what is the final price?", "check": lambda r: "81,480" in r or "81480" in r.replace(",", "")},
        {"id": "math_04", "prompt": "Solve for x: 3x - 7 = 2x + 5. Give only x.", "check": lambda r: "12" in r},
        {"id": "math_05", "prompt": "A trader has a 55% win rate with an average win of $200 and average loss of $150. What is the Expected Value per trade?", "check": lambda r: "42.50" in r or "42.5" in r},
    ],
    "TRADING_REASONING": [
        {"id": "trade_01", "prompt": "RSI is 28, price is touching the lower Bollinger Band, ADX is 14, volume ratio 0.8. What strategy fits best? One sentence.", "check": lambda r: ("mean reversion" in r.lower() or "oversold" in r.lower()) and ("buy" in r.lower() or "long" in r.lower())},
        {"id": "trade_02", "prompt": "BTC EMA50 above EMA200, ADX=32, RSI=62, volume=1.5x. Market regime and bias? One sentence.", "check": lambda r: ("trend" in r.lower() or "bullish" in r.lower()) and ("long" in r.lower() or "buy" in r.lower())},
        {"id": "trade_03", "prompt": "Kelly says 8% of portfolio. Your cap is 2%. Which do you follow and why? One sentence.", "check": lambda r: "2%" in r or "2 percent" in r.lower() or "cap" in r.lower() or "rule" in r.lower()},
        {"id": "trade_04", "prompt": "Signal confidence 0.45. ACCEPTED threshold is 0.52. What verdict? One sentence.", "check": lambda r: ("watch" in r.lower() or "reject" in r.lower() or "hold" in r.lower()) and ("threshold" in r.lower() or "below" in r.lower())},
        {"id": "trade_05", "prompt": "Baseline BUY conf 0.65. LLM SELL conf 0.75. Veto model: final signal? One sentence.", "check": lambda r: ("watch" in r.lower() or "hold" in r.lower()) and ("veto" in r.lower() or "oppos" in r.lower() or "cancel" in r.lower())},
        {"id": "trade_06", "prompt": "SOL breaks below 200-day EMA on high volume. ADX is 38. What does this signal? One sentence.", "check": lambda r: ("bearish" in r.lower() or "breakdown" in r.lower() or "short" in r.lower()) and ("ema" in r.lower() or "200" in r)},
    ],
    "FACTUAL": [
        {"id": "fact_01", "prompt": "What does RSI measure in technical analysis? One sentence.", "check": lambda r: ("momentum" in r.lower() or "speed" in r.lower() or "strength" in r.lower()) and "price" in r.lower()},
        {"id": "fact_02", "prompt": "What is the standard interpretation when the 50-day EMA crosses above the 200-day EMA? One sentence.", "check": lambda r: "golden cross" in r.lower() or "bullish" in r.lower() or "buy" in r.lower()},
        {"id": "fact_03", "prompt": "In algorithmic trading, what is slippage? One sentence.", "check": lambda r: "differ" in r.lower() and ("expect" in r.lower() or "intend" in r.lower()) and ("price" in r.lower() or "execut" in r.lower())},
        {"id": "fact_04", "prompt": "What does ADX measure and what value indicates a strong trend? One sentence.", "check": lambda r: "trend" in r.lower() and "strength" in r.lower() and ("25" in r or "20" in r)},
    ],
    "INSTRUCTION_FOLLOWING": [
        {"id": "instr_01", "prompt": 'Return exactly: {"signal": "BUY", "confidence": 0.72, "pair": "BTC/USDT"}. No other text.', "check": lambda r: '"signal"' in r and '"BUY"' in r and '"BTC/USDT"' in r},
        {"id": "instr_02", "prompt": "List exactly 3 risks of leverage in crypto trading. Number them 1-3. No other text.", "check": lambda r: ("1." in r or "1)" in r) and ("2." in r or "2)" in r) and ("3." in r or "3)" in r)},
        {"id": "instr_03", "prompt": "Respond with only the word PASS. No other text.", "check": lambda r: r.strip().upper() == "PASS"},
    ],
}

# Models to compare
MODELS = [
    # Z.AI GLM-5.1 (baseline)
    {"name": "glm-5.1", "provider": "zai", "model": "glm-5.1"},
    # DeepSeek
    {"name": "deepseek-v4-flash", "provider": "deepseek", "model": "deepseek-v4-flash"},
    {"name": "deepseek-v3-0324", "provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324"},
    # OpenRouter free
    {"name": "gpt-4o-mini", "provider": "openrouter", "model": "openai/gpt-4o-mini"},
    {"name": "claude-3-haiku", "provider": "openrouter", "model": "anthropic/claude-3-haiku"},
    {"name": "mistral-nemo", "provider": "openrouter", "model": "mistralai/mistral-nemo"},
    {"name": "llama-3.1-8b", "provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct"},
]

def run_model(model_cfg: dict) -> dict:
    name = model_cfg["name"]
    provider = model_cfg["provider"]
    model = model_cfg["model"]
    key, base_url = load_api_creds(provider)

    print(f"\n  Testing {name}...", flush=True)
    results = {}
    cat_scores = {}
    total_correct = 0
    total_questions = 0
    total_time = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for cat, questions in BENCHMARKS.items():
        cat_correct = 0
        for q in questions:
            t0 = time.time()
            resp = call_model(base_url, key, model, q["prompt"])
            elapsed = time.time() - t0
            content = resp.get("content", "")
            passed = q["check"](content) if resp["success"] else False
            usage = resp.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_time += elapsed
            if passed:
                cat_correct += 1
                total_correct += 1
            total_questions += 1
            time.sleep(1.5)  # rate limit courtesy
        cat_scores[cat] = f"{cat_correct}/{len(questions)}"

    return {
        "name": name,
        "model": model,
        "provider": provider,
        "total_correct": total_correct,
        "total_questions": total_questions,
        "accuracy": round(total_correct / total_questions * 100, 1),
        "cat_scores": cat_scores,
        "total_time_s": round(total_time, 1),
        "avg_latency_s": round(total_time / total_questions, 1),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
    }

def main():
    all_results = []
    for cfg in MODELS:
        try:
            r = run_model(cfg)
            all_results.append(r)
            print(f"    -> {r['total_correct']}/{r['total_questions']} ({r['accuracy']}%) | {r['avg_latency_s']}s avg")
        except Exception as e:
            print(f"    FAILED: {e}")

    # Sort by accuracy desc
    all_results.sort(key=lambda x: x["accuracy"], reverse=True)

    print("\n" + "=" * 80)
    print("  MULTI-MODEL BENCHMARK — TRADING-RELEVANT TASKS")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)
    print(f"\n  {'Rank':<5} {'Model':<22} {'Acc':<6} {'MATH':<7} {'TRADE':<7} {'FACT':<7} {'INST':<7} {'AvgS':<6} {'Tokens'}")
    print(f"  {'-'*5} {'-'*22} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*6} {'-'*10}")
    for i, r in enumerate(all_results, 1):
        math_s = r['cat_scores'].get('MATH', '?')
        trade_s = r['cat_scores'].get('TRADING_REASONING', '?')
        fact_s = r['cat_scores'].get('FACTUAL', '?')
        inst_s = r['cat_scores'].get('INSTRUCTION_FOLLOWING', '?')
        print(f"  {i:<5} {r['name']:<22} {r['accuracy']:>5.1f}% {math_s:<7} {trade_s:<7} {fact_s:<7} {inst_s:<7} {r['avg_latency_s']:>5.1f}s {r['total_prompt_tokens']+r['total_completion_tokens']:>9}")

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"multi_model_benchmark_{ts}.json"
    out.write_text(json.dumps({"results": all_results, "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2))
    print(f"\n  Results: {out}")

if __name__ == "__main__":
    main()