import json
import sys
from pathlib import Path

def generate_ascii_bar(value, max_value, width=40):
    if max_value == 0:
        return ""
    bar_length = int((value / max_value) * width)
    return "█" * bar_length + "░" * (width - bar_length)

def visualize_session_tokens(session_dir):
    log_dir = Path(session_dir) / "logs"
    if not log_dir.exists():
        print(f"Error: Log directory not found in {session_dir}")
        return

    # Find the latest log run
    run_dirs = sorted(log_dir.iterdir(), key=lambda x: x.name, reverse=True)
    if not run_dirs:
        print("No runs found.")
        return
    
    events_file = run_dirs[0] / "events.jsonl"
    if not events_file.exists():
        print(f"No events.jsonl in {run_dirs[0]}")
        return

    turns = []
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            if event["event_type"] == "model_request":
                payload = event["payload"]
                # For newer logs with token_count, use it. 
                # For older ones, estimate from context_prompt length
                tokens = payload.get("token_count")
                if tokens is None:
                    tokens = len(payload.get("context_prompt", "")) // 2
                
                turns.append({
                    "turn": payload.get("turn_index"),
                    "tokens": tokens
                })

    if not turns:
        print("No token data found in events.")
        return

    max_tokens = max(t["tokens"] for t in turns)
    print(f"\n=== Token Usage Trend: {session_dir.name} ===")
    print(f"{'Turn':<5} | {'Tokens':<8} | {'Scale'}")
    print("-" * 60)
    for t in turns:
        bar = generate_ascii_bar(t["tokens"], max_tokens)
        print(f"{t['turn']:<5} | {t['tokens']:<8,} | {bar}")
    print("-" * 60)
    print(f"Peak Tokens: {max_tokens:,}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_tokens.py <session_path>")
    else:
        visualize_session_tokens(Path(sys.argv[1]))
