#!/usr/bin/env python3
"""Build a reproducible Korean typo benchmark from KLUE-YNAT titles.

KLUE is CC-BY-SA-4.0. This script downloads the public dataset through
Hugging Face Datasets and exports first-party-derived JSONL inputs for
benchmark.py. It uses token-level retrieval and synthetic Hangul-syllable
substitution errors; it does not claim to model naturally occurring Korean
typing errors.
"""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from datasets import load_dataset


TOKEN_RE = re.compile(r"[가-힣]{2,}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/korean")
    parser.add_argument("--max-docs", type=int, default=100000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--min-frequency", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if min(args.max_docs, args.queries, args.min_frequency) < 1:
        parser.error("max-docs, queries, and min-frequency must be positive")

    train = load_dataset("klue/klue", "ynat", split="train")
    validation = load_dataset("klue/klue", "ynat", split="validation")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    docs = []
    for row in list(train) + list(validation):
        title = row["title"].strip()
        if title:
            docs.append({"id": str(row["guid"]), "content": title})
    docs = docs[:args.max_docs]
    if not docs:
        parser.error("KLUE yielded no non-empty titles")

    frequencies = Counter()
    first_doc = {}
    for doc in docs:
        for token in set(TOKEN_RE.findall(doc["content"])):
            frequencies[token] += 1
            first_doc.setdefault(token, doc["id"])

    candidates = sorted(
        token for token, freq in frequencies.items()
        if freq >= args.min_frequency and len(token) >= 3
    )
    if not candidates:
        parser.error("no Korean terms meet the minimum frequency/length")

    rng = random.Random(args.seed)
    chosen = rng.sample(candidates, min(args.queries, len(candidates)))
    corpus_path = out / "corpus.jsonl"
    queries_path = out / "queries.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    query_rows = []
    for clean in chosen:
        relevant = [first_doc[clean]]
        query_rows.append({"clean": clean, "typo": clean,
                           "relevant_ids": relevant, "bucket": "clean"})
        for edits in (1, 2, 3):
            syllables = list(clean)
            positions = rng.sample(range(len(syllables)), edits)
            for position in positions:
                syllables[position] = chr(rng.randrange(0xAC00, 0xD7A4))
            typo = "".join(syllables)
            if typo != clean:
                query_rows.append({"clean": clean, "typo": typo,
                                   "relevant_ids": relevant,
                                   "bucket": f"typo_{edits}"})
    with queries_path.open("w", encoding="utf-8") as f:
        for row in query_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    metadata = {
        "dataset": "klue/klue",
        "config": "ynat",
        "license": "CC-BY-SA-4.0",
        "source": "KLUE-Y 데이터 title fields from train then validation",
        "docs": len(docs),
        "vocabulary_terms": len(frequencies),
        "candidate_terms": len(candidates),
        "query_terms": len(chosen),
        "query_rows": len(query_rows),
        "min_frequency": args.min_frequency,
        "seed": args.seed,
        "typo_generation": "replace 1/2/3 randomly selected Hangul syllable blocks with random precomposed Hangul syllables",
        "note": "Synthetic syllable substitutions, not naturally observed typos; evaluate only retrieval on this derived task.",
    }
    (out / "dataset.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    results_dir = Path("results/korean")
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "dataset.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print("corpus:", corpus_path, "queries:", queries_path)


if __name__ == "__main__":
    main()
