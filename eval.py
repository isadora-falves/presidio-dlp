"""Measures dlp.engine's Precision/Recall/F1 against a hand-written gold
standard (eval_gold.py), using the same scoring logic the assignment
describes:

  TP = entity replaced in full and with the correct label.
  FN = missed, partially replaced, or tagged with the wrong label.
  FP = an uncalled-for substitution, or the wrong label.

This is not the professor's oracle — it's our own gold standard, meant to
measure the real impact of what we already know is missing (see LIM-1,
LIM-2 in the bitácora) instead of just saying "I tried it and it works".

Usage: python eval.py
"""

from pathlib import Path

from dlp.engine import find_entities
from eval_gold import GOLD

EXAMPLES_DIR = Path(__file__).parent / "examples"


def _resolve(text: str, gold: list[tuple[str, str]]) -> set[tuple[int, int, str]]:
    spans = set()
    cursor = 0
    for substring, label in gold:
        start = text.index(substring, cursor)
        end = start + len(substring)
        spans.add((start, end, label))
        cursor = end
    return spans


def score_file(filename: str) -> dict:
    text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8-sig")
    gold_spans = _resolve(text, GOLD[filename])
    predicted_spans = set(find_entities(text))

    tp = gold_spans & predicted_spans
    fn = gold_spans - predicted_spans
    fp = predicted_spans - gold_spans
    return {"tp": tp, "fn": fn, "fp": fp, "text": text}


def _prf1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def main() -> None:
    total_tp = total_fp = total_fn = 0
    for filename in GOLD:
        result = score_file(filename)
        tp, fp, fn = len(result["tp"]), len(result["fp"]), len(result["fn"])
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision, recall, f1 = _prf1(tp, fp, fn)
        print(f"{filename:32s} TP={tp:2d} FP={fp:2d} FN={fn:2d}  "
              f"P={precision:.2f} R={recall:.2f} F1={f1:.2f}")
        for start, end, label in sorted(result["fp"]):
            print(f"    FP: {label:8s} {result['text'][start:end]!r}")
        for start, end, label in sorted(result["fn"]):
            print(f"    FN: {label:8s} {result['text'][start:end]!r}")

    precision, recall, f1 = _prf1(total_tp, total_fp, total_fn)
    print("-" * 70)
    print(f"{'TOTAL':32s} TP={total_tp:2d} FP={total_fp:2d} FN={total_fn:2d}  "
          f"P={precision:.2f} R={recall:.2f} F1={f1:.2f}")


if __name__ == "__main__":
    main()
