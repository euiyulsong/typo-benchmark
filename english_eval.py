#!/usr/bin/env python3
"""Build a token-retrieval benchmark from the public AG News dataset.

AG News is distributed by Hugging Face as `fancyzhx/ag_news` under MIT.
The corpus exports only source text and deterministic synthetic typos.
"""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from datasets import load_dataset


TOKEN_RE = re.compile(r"[A-Za-z]{3,}")
ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/english")
    parser.add_argument("--max-docs", type=int, default=50000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--min-frequency", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if min(args.max_docs, args.queries, args.min_frequency) < 1:
        parser.error("max-docs, queries, and min-frequency must be positive")

    dataset = load_dataset("fancyzhx/ag_news")
    rows = list(dataset["train"]) + list(dataset["test"])
    docs = [{"id": str(i), "content": row["text"].strip()}
            for i, row in enumerate(rows) if row["text"].strip()][:args.max_docs]
    if not docs:
        parser.error("AG News yielded no non-empty documents")

    frequencies = Counter()
    first_doc = {}
    for doc in docs:
        for token in set(TOKEN_RE.findall(doc["content"].lower())):
            frequencies[token] += 1
            first_doc.setdefault(token, doc["id"])
    candidates = sorted(token for token, freq in frequencies.items()
                        if freq >= args.min_frequency)
    if not candidates:
        parser.error("no English terms meet the minimum frequency")

    rng = random.Random(args.seed)
    chosen = rng.sample(candidates, min(args.queries, len(candidates)))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "corpus.jsonl").open("w", encoding="utf-8") as stream:
        for doc in docs:
            stream.write(json.dumps(doc, ensure_ascii=False) + "\n")

    query_rows = []
    for clean in chosen:
        relevant = [first_doc[clean]]
        query_rows.append({"clean": clean, "typo": clean,
                           "relevant_ids": relevant, "bucket": "clean"})
        for edits in (1, 2, 3):
            letters = list(clean)
            for position in rng.sample(range(len(letters)), min(edits, len(letters))):
                letters[position] = rng.choice([c for c in ALPHABET if c != letters[position]])
            typo = "".join(letters)
            if typo != clean:
                query_rows.append({"clean": clean, "typo": typo,
                                   "relevant_ids": relevant,
                                   "bucket": f"typo_{edits}"})
    with (out / "queries.jsonl").open("w", encoding="utf-8") as stream:
        for row in query_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    metadata = {
        "dataset": "fancyzhx/ag_news",
        "license": "MIT (dataset card; verify upstream terms before redistribution)",
        "source": "AG News train and test text fields",
        "docs": len(docs), "vocabulary_terms": len(frequencies),
        "candidate_terms": len(candidates), "query_terms": len(chosen),
        "query_rows": len(query_rows), "min_frequency": args.min_frequency,
        "seed": args.seed,
        "typo_generation": "replace 1/2/3 randomly selected ASCII letters with other lowercase letters",
        "note": "Synthetic character substitutions, not naturally observed typos; qrels point to the first document containing the clean term.",
    }
    (out / "dataset.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("corpus:", out / "corpus.jsonl", "queries:", out / "queries.jsonl")


if __name__ == "__main__":
    main()
