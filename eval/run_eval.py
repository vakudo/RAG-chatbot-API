"""Mini-eval: runs questions against the live API and checks the answers
contain expected keywords. Usage:

    python eval/run_eval.py [--base http://localhost:8000]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def ask(base: str, question: str) -> str:
    answer = []
    with httpx.stream(
        "POST",
        f"{base}/chat",
        json={"question": question, "history": []},
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            if "content" in event:
                answer.append(event["content"])
    return "".join(answer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()

    cases = json.loads(
        (Path(__file__).parent / "questions.json").read_text(encoding="utf-8")
    )
    passed = 0
    for case in cases:
        started = time.monotonic()
        try:
            answer = ask(args.base, case["question"])
        except Exception as exc:
            print(f"[FAIL] {case['question']}\n       error: {exc}")
            continue
        elapsed = time.monotonic() - started
        ok = any(k.lower() in answer.lower() for k in case["expected_keywords"])
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] ({elapsed:4.1f}s) {case['question']}")
        if not ok:
            print(f"       expected one of: {case['expected_keywords']}")
            print(f"       got: {answer[:200]}")

    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
