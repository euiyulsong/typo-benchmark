#!/usr/bin/env python3
"""Write a compact method/bucket summary from benchmark CSV files."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary_csv', type=Path)
    parser.add_argument('--docs', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.summary_csv.open(encoding='utf-8', newline='')))
    by_method = defaultdict(dict)
    expected = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if int(row['docs']) == args.docs:
            by_method[row['method']][row['bucket']] = row
            expected[row['method']][row['bucket']] += int(row['samples'])
    buckets = ['clean', 'typo_1', 'typo_2', 'typo_3']
    with args.output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['method', 'bucket', 'samples', 'expected_samples', 'coverage', 'errors', 'mrr_at_k', 'hit_at_k', 'p50_ms', 'p95_ms', 'max_ms', 'correction_accuracy', 'false_correction_rate', 'candidate_recall', 'index_bytes', 'index_seconds'])
        for method in sorted(by_method):
            for bucket in buckets:
                row = by_method[method].get(bucket)
                if row:
                    samples = int(row['samples'])
                    expected_samples = expected[method][bucket]
                    writer.writerow([method, bucket, samples, expected_samples, round(samples/expected_samples, 4) if expected_samples else '', *[row.get(k, '') for k in ('errors', 'mrr_at_k', 'hit_at_k', 'p50_ms', 'p95_ms', 'max_ms', 'correction_accuracy', 'false_correction_rate', 'candidate_recall', 'index_bytes', 'index_seconds')]])
    print(f'Wrote {args.output} ({len(by_method)} methods, {args.docs} docs)')


if __name__ == '__main__':
    main()
