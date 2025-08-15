from typing import Dict

def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    # Rough heuristic: ~4 chars per token average
    return max(1, int(len(text) / 4))


def ensure_usage(state: Dict) -> Dict:
    usage = state.get("usage") or {}
    usage.setdefault("estimated_input_tokens", 0)
    usage.setdefault("estimated_output_tokens", 0)
    usage.setdefault("llm_calls", 0)
    return usage


def add_llm_usage(state: Dict, prompt_chars: int, output_chars: int):
    usage = ensure_usage(state)
    usage["estimated_input_tokens"] += estimate_tokens_from_text("x" * prompt_chars)
    usage["estimated_output_tokens"] += estimate_tokens_from_text("x" * output_chars)
    usage["llm_calls"] += 1
    state["usage"] = usage
    return state
