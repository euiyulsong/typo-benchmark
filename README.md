# Typo Search Benchmark — 2026-10-13 실험 결과

Elasticsearch BM25를 기준으로 오타 검색 방법의 **최종 검색 품질과 지연**을 비교합니다. 이전 README는 [`README.temporary.md`](README.temporary.md)에 보존했습니다. 이 문서는 오늘 재실행한 영어·한국어 실험의 결과를 요약합니다.

## 요약

- Elasticsearch 8.15.5 단일 노드에서 기존 방식에 fuzzy `AUTO`, term suggester `always`, completion suggester, Elasticsearch character n-gram, 병렬 RRF 조합을 더해 측정했습니다.
- 한국어 corpus는 1k/10k/50k에서 85개 method 전부 완료했습니다(오류 0건).
- 영어 corpus도 1k/10k/50k까지 색인했습니다. 50k 단계에서는 비용이 큰 Python n-gram/SymSpell 조합을 포함해 일부 method가 실행 제한의 영향을 받았습니다. 50k 요약에는 22개 method가 있고 4개 bucket 합계 오류는 119건(ngram_2-3_d3)입니다. method별 sample·오류 수를 확인하세요.
- 저장소의 실제 corpus는 언어별 50,000문서입니다. 100,000,000문서 실험은 데이터가 없어 실행하지 않았습니다.
- 모든 query는 합성 문자 치환 오타이며, 결과는 자연 오타/서비스 품질을 대표하지 않습니다.

## 50k 결과: 1자 오타

Hit@10/MRR@10은 최종 검색 결과 지표이고, p95는 교정/제안 단계를 포함한 client end-to-end 지연(ms)입니다. 언어별 typo_1 100개 query이며 같은 query를 여러 번 반복해 독립 표본을 늘린 실험은 아닙니다.

| 언어 | 방법 | Hit@10 | MRR@10 | p95 (ms) |
|---|---|---:|---:|---:|
| 한국어 | BM25 raw | 0% | 0.000 | 1.16 |
| 한국어 | Elasticsearch fuzzy d1 | **74%** | **0.450** | **2.87** |
| 한국어 | Elasticsearch fuzzy d2 | 75% | 0.419 | 5.42 |
| 한국어 | fuzzy AUTO | 74% | 0.445 | 4.66 |
| 한국어 | term suggester d1 → BM25 | 66% | 0.448 | 3.82 |
| 한국어 | Python SymSpell d2 | 58% | 0.400 | 1.72 |
| 한국어 | Python bigram correction d1 | 53% | 0.361 | 1.70 |
| 한국어 | Python unigram correction d1 | 58% | 0.400 | 17.92 |
| 한국어 | Elasticsearch n-gram direct d1 | 0% | 0.000 | 1.27 |
| 한국어 | BM25 + ES n-gram 병렬 RRF d1 | 0% | 0.000 | 1.71 |
| 한국어 | fuzzy + ES n-gram 병렬 RRF d1 | 74% | 0.450 | 3.30 |
| 한국어 | fuzzy + BM25 병렬 RRF d1 | 74% | 0.450 | 3.48 |
| 영어 | BM25 raw | 0% | 0.000 | 1.29 |
| 영어 | Elasticsearch fuzzy d1 | **36%** | **0.207** | **1.74** |
| 영어 | Elasticsearch fuzzy d2 | 36% | 0.172 | 3.76 |
| 영어 | fuzzy AUTO | 40% | 0.197 | 3.80 |
| 영어 | Elasticsearch n-gram direct d1 | 0% | 0.000 | 1.44 |

영어 50k의 fuzzy+ES n-gram 병렬 조합은 완료된 유효 결과가 없어 표에서 제외했습니다. 전체 결과는 `results/english-final/summary-50000.csv`에서 확인하세요.

### 해석

1. 이번 한국어 표본에서는 fuzzy d1이 단순하고 빠른 기준점이었습니다. fuzzy+ngram 병렬 조합은 품질을 높이지 못했고 p95가 2.87ms에서 3.30ms로 늘었습니다.
2. ES n-gram direct와 BM25+ngram 조합은 typo_1 관련 문서를 찾지 못했습니다. n-gram은 문자 부분 일치 검색이지 이 설정에서 보정어를 생성하는 교정기와 같지 않습니다.
3. Python n-gram은 설정에 따라 품질과 속도 편차가 큽니다. 특히 unigram은 한국어 50k에서 p95 17.92ms, 영어 10k에서 p95 약 69.6ms까지 증가했습니다.
4. 한국어 term suggester `suggest_mode=always`는 clean 입력을 과잉 수정했습니다. 50k clean Hit@10이 약 18%였으므로 기본 경로로 쓰기 어렵습니다.
5. Completion suggester는 prefix 자동완성입니다. 오타 교정 방식이 아니며, typo query에서 관련 검색 결과를 거의 내지 못했습니다.

## 재현 및 산출물

전체 bucket별 summary, query별 samples, Elasticsearch 버전·설정은 다음 경로에 있습니다.

- [한국어 전체 결과](results/korean-final/): `summary.csv`, `samples.csv`, `run.json`, [50k compact summary](results/korean-final/summary-50000.csv)
- [영어 전체 결과](results/english-final/): `summary.csv`, `samples.csv`, `run.json`, [50k compact summary](results/english-final/summary-50000.csv)
- 기존 README: [README.temporary.md](README.temporary.md)

저장 corpus를 이용한 한국어 실행 명령:

```bash
python3 benchmark.py \
  --corpus data/korean/corpus.jsonl --queries data/korean/queries.jsonl \
  --sizes 1000,10000,50000 --edits 0,1,2,3 \
  --grams 1,2,3,4,2-3,2-4 --samples 100 --repeats 1 \
  --hybrid --auto --es-ngram --oom-rss-mib 8192 \
  --max-method-seconds 45 --timeout 30 --output results/korean-new
```

영어는 corpus/query 경로와 output 폴더를 `data/english/...`, `results/english-new`로 바꾸면 됩니다. `--max-method-seconds`는 method 구축/평가 시간을 제한하며, `run.json`/요약 CSV에서 실행 범위와 coverage를 확인하세요. `--oom-rss-mib`는 benchmark 프로세스의 최대 RSS guard이며 Elasticsearch heap/컨테이너 OOM은 별도 감시가 필요합니다.

## 지표와 한계

- `hit_at_k`, `mrr_at_k`: 최종 검색 품질. 교정 성공률과 별개입니다.
- `p50_ms`, `p95_ms`, `max_ms`: client end-to-end 지연. 병렬 조합의 client latency와 ES `took` 합계는 의미가 다릅니다.
- `correction_accuracy`, `false_correction_rate`, `candidate_recall`: 교정/후보 방식에 대한 진단 지표입니다.
- `index_bytes`, `index_seconds`: 추가 n-gram/completion 필드를 포함한 ES 색인 비용입니다.
- `samples.csv`의 오류와 summary sample 수를 확인하세요. 오류가 있는 표본은 지연 percentile에서 제외됩니다.

실험은 1 shard, 단일 노드, whitespace analyzer, top-10, 합성 치환 오타, query당 제한된 qrels를 사용했습니다. 언어별 실제 오타, analyzer, shard 수, 동시성, relevance 판단을 대표하지 않습니다. 따라서 작은 점수 차이를 일반적인 방법 우위로 해석하지 마세요. 1억 문서 비교에는 해당 크기의 corpus와 별도 용량의 Elasticsearch가 필요합니다.
