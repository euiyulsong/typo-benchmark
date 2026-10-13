# Typo Search Benchmark — 실험 결과 (2026-10-13, 추가 term/fuzzy AUTO 실험)

Elasticsearch BM25를 기준으로 오타 검색 방법의 **최종 검색 품질과 지연**을 비교합니다. 기존 README는 [`README.temporary.md`](README.temporary.md)에 보존했습니다.

## 이번 실험 구성

- Elasticsearch 8.15.5 단일 노드, 1 shard, top-10 검색
- 영어/한국어 공개 뉴스 corpus 각각 최대 50,000문서
- 1,000 / 10,000 / 50,000문서 단계, edits 0–3, Python n-gram 1/2/3/4/2-3/2-4
- 기본 그리드 85 methods: raw/oracle BM25, fuzzy d1/d2, fuzzy AUTO, term suggestion, completion, SymSpell, Python n-gram, ES n-gram, raw/fuzzy/suggestion 병렬 RRF 조합
- 추가 12 variants: term suggestion → fuzzy AUTO의 d1/d2, term suggestion → fixed fuzzy, term→BM25, term→fuzzy+BM25 parallel, fuzzy AUTO+BM25 RRF 등
- bucket별 100 query, repeats=1. Queries는 문자 치환 방식으로 만든 합성 오타이며 자연 오타가 아닙니다.

한국어와 영어 모두 기본 1k/10k/50k 그리드의 85개 method 전부 완료했습니다. 추가 term/fuzzy AUTO 비교는 양 언어 50k에서 12개 method, bucket별 300회(100 query × 3 repeats)로 실행했으며 API 오류는 없었습니다. 추가 결과는 [영어](results/english-term-fuzzy-auto/), [한국어](results/korean-term-fuzzy-auto/)에 저장했습니다. 이전 영어 결과 [`results/english-final/`](results/english-final/)는 첫 전체 실행의 오류 이력을 비교할 수 있게 보존합니다.

## 50k 결과: 1자 오타

Hit@10/MRR@10은 최종 검색 품질이며, p95는 교정/제안과 검색을 포함한 client end-to-end latency(ms)입니다. 각 언어의 typo_1은 100 query입니다.

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
| 영어 (이전 run) | BM25 raw | 0% | 0.000 | 1.29 |
| 영어 (이전 run) | Elasticsearch fuzzy d1 | **36%** | **0.207** | **1.74** |
| 영어 (이전 run) | Elasticsearch fuzzy d2 | 36% | 0.172 | 3.76 |
| 영어 (이전 run) | fuzzy AUTO | 40% | 0.197 | 3.80 |
| 영어 (이전 run) | Elasticsearch n-gram direct d1 | 0% | 0.000 | 1.44 |
| 영어 (신규 run) | BM25 raw | 0% | 0.000 | 1.14 |
| 영어 (신규 run) | Elasticsearch fuzzy d1 | **36%** | **0.207** | **1.57** |
| 영어 (신규 run) | Elasticsearch fuzzy d2 | 36% | 0.172 | 3.40 |
| 영어 (신규 run) | fuzzy AUTO d1 | 40% | 0.197 | 3.51 |
| 영어 (신규 run) | Python SymSpell d2 | 43% | 0.239 | 1.47 |
| 영어 (신규 run) | Python unigram correction d1 | 33% | 0.181 | 194.20 |
| 영어 (신규 run) | Python bigram correction d1 | 34% | 0.191 | 64.69 |
| 영어 (신규 run) | Python 2–3-gram correction d1 | 34% | 0.191 | 84.40 |
| 영어 (신규 run) | Elasticsearch n-gram direct d1 | 0% | 0.000 | 1.40 |
| 영어 (신규 run) | BM25 + ES n-gram parallel RRF d1 | 0% | 0.000 | 1.74 |
| 영어 (신규 run) | fuzzy + ES n-gram 병렬 RRF d1 | 36% | 0.207 | 2.95 |
| 영어 (신규 run) | fuzzy + BM25 병렬 RRF d1 | 36% | 0.207 | 2.58 |
| 영어 (신규 run) | term suggester d1 → BM25 | 34% | 0.191 | 2.54 |
| 영어 (신규 run) | completion suggester | 0% | 0.000 | 2.13 |

영어 fuzzy d1의 신규 p95 1.57ms는 기존 run의 1.74ms와 일부 다릅니다(같은 50k corpus, 서로 다른 실행 시점). 이전 영어 값은 실험 이력 비교용이며, 결론은 신규 실행 결과를 기준으로 합니다.

## 추가 실험: term suggestion + fuzzy AUTO variant (50k)

요청에 따라 clean 입력과 1/2/3자 typo bucket을 모두 포함해 양 언어 50k corpus에서 추가 비교했습니다. 12 methods × bucket별 100개 query × 3 repeats(요약 CSV의 `samples=300`), API 오류 0건입니다. Hit@10/MRR@10은 최종 검색 품질, p95는 suggestion과 retrieval을 포함한 end-to-end latency(ms)입니다. `Term→AUTO d1/d2`는 term suggester로 후보 correction을 고른 뒤 Elasticsearch fuzzy `AUTO` 검색을 수행합니다.

| 언어 | Variant | clean Hit@10 (false correction) | typo_1 Hit@10 / MRR | typo_2 Hit@10 / MRR | typo_3 Hit@10 / MRR | p95 ms (clean / 1 / 2 / 3) |
|---|---|---:|---:|---:|---:|---:|
| 영어 | BM25 raw | 39% (0%) | 0% / 0.000 | 0% / 0.000 | 0% / 0.000 | 1.95 / 1.72 / 1.69 / 1.78 |
| 영어 | Fuzzy AUTO d1 | 37% (0%) | 40% / 0.197 | 25% / 0.123 | 0% / 0.000 | 4.16 / 3.93 / 3.99 / 3.46 |
| 영어 | Term→BM25 (`term_d1`) | 54% (30%) | 34% / 0.191 | 0% / 0.000 | 0% / 0.000 | 2.39 / 2.62 / 2.43 / 2.30 |
| 영어 | Term→fixed fuzzy d1 | 51% (30%) | 36% / 0.169 | 0% / 0.000 | 0% / 0.000 | 2.37 / 2.52 / 2.38 / 2.39 |
| 영어 | Term→fuzzy AUTO d1 | 36% (92%) | 30% / 0.157 | 25% / 0.123 | 0% / 0.000 | 3.87 / 4.01 / 3.90 / 3.80 |
| 영어 | Term→fuzzy AUTO d2 | 34% (97%) | 27% / 0.148 | 21% / 0.109 | 0% / 0.000 | 5.13 / 5.14 / 5.27 / 5.00 |
| 영어 | Term→(fuzzy AUTO + BM25 RRF) d1 | 35% (92%) | **43% / 0.218** | 25% / 0.123 | 0% / 0.000 | 5.22 / 5.04 / 5.01 / 5.00 |
| 영어 | Fuzzy AUTO + BM25 RRF d1 | **55% (0%)** | 40% / 0.197 | 25% / 0.123 | 0% / 0.000 | 4.74 / 4.48 / 4.57 / 4.51 |
| 한국어 | BM25 raw | 81% (0%) | 0% / 0.000 | 0% / 0.000 | 0% / 0.000 | 2.00 / 1.89 / 1.92 / 1.87 |
| 한국어 | Fuzzy AUTO d1 | **82% (0%)** | 74% / 0.445 | 6% / 0.045 | 0% / 0.000 | 3.89 / 4.01 / 3.71 / 3.69 |
| 한국어 | Term→BM25 (`term_d1`) | 81% (2%) | 66% / 0.448 | 0% / 0.000 | 0% / 0.000 | 2.37 / 2.75 / 2.76 / 2.63 |
| 한국어 | Term→fixed fuzzy d1 | 82% (2%) | 71% / 0.453 | 0% / 0.000 | 0% / 0.000 | 2.81 / 3.30 / 3.01 / 2.95 |
| 한국어 | Term→fuzzy AUTO d1 | 44% (79%) | 71% / 0.453 | 6% / 0.045 | 0% / 0.000 | 5.14 / 4.93 / 4.86 / 4.70 |
| 한국어 | Term→fuzzy AUTO d2 | 36% (93%) | 71% / 0.453 | 19% / 0.115 | 0% / 0.000 | 6.05 / 5.88 / 5.79 / 5.72 |
| 한국어 | Term→(fuzzy AUTO + BM25 RRF) d1 | 44% (79%) | 71% / **0.462** | 6% / 0.045 | 0% / 0.000 | 6.06 / 5.87 / 5.63 / 5.64 |
| 한국어 | Fuzzy AUTO + BM25 RRF d1 | **82% (0%)** | **74% / 0.445** | 6% / 0.045 | 0% / 0.000 | 4.58 / 4.61 / 4.62 / 4.35 |

추가 비교에서 term suggestion을 AUTO fuzzy에 앞세운 것은 두 언어 모두 clean query를 크게 훼손했습니다(영어 false correction 92–97%, 한국어 79–93%). typo_1에서도 suggestion 없는 fuzzy AUTO보다 품질 우위가 없고 더 느렸습니다. d2는 영어 typo_2를 21%까지 찾았지만 p95 5.27ms였고, 한국어는 19%였지만 p95 5.79ms였습니다. d3 typo는 이 단어 단위 whitespace 실험의 모든 비교군에서 Hit@10 0%였습니다. 따라서 term suggestion 결과를 무조건 적용하는 조합은 기본 경로로 권하지 않습니다. 실제 서비스라면 confidence/원문 병행 검색, analyzer 및 다중 토큰 query를 별도로 평가해야 합니다.

### 관찰

1. 한국어 표본에서는 fuzzy d1이 품질·속도의 균형이 가장 좋은 기준점이었습니다. fuzzy+ngram RRF는 품질 향상 없이 p95가 2.87ms에서 3.30ms로 늘었습니다.
2. ES n-gram 직접 검색과 BM25+ngram 조합은 영어·한국어 모두 이 합성 typo_1 query에서 관련 문서를 찾지 못했습니다. 검색용 문자 n-gram은 교정 후보 생성기와 같은 방식이 아닙니다.
3. Python unigram 후보 교정은 한국어 50k p95 17.92ms, 영어 신규 50k p95 194.20ms였습니다. 영어 bigram도 p95 64.69ms였으며, 어휘 크기와 흔한 gram의 후보 폭이 성능에 크게 영향을 줍니다.
4. 한국어 term suggester `suggest_mode=always`는 clean query 과잉 수정이 커 clean Hit@10이 18%에 그쳤습니다.
5. Completion suggester는 prefix 자동완성이지 typo 교정기가 아니므로 typo 검색 품질과 직접 비교할 때 주의해야 합니다.

## 결과 파일과 실행

- [한국어 완료 결과](results/korean-final/): `summary.csv`, `samples.csv`, `run.json`, [50k compact summary](results/korean-final/summary-50000.csv)
- [영어 신규 전체 실행](results/english-complete/): [summary.csv](results/english-complete/summary.csv), [samples.csv](results/english-complete/samples.csv), [run.json](results/english-complete/run.json), [50k compact summary](results/english-complete/summary-50000.csv)
- [영어 term/fuzzy AUTO 추가 실험](results/english-term-fuzzy-auto/): [summary.csv](results/english-term-fuzzy-auto/summary.csv), [samples.csv](results/english-term-fuzzy-auto/samples.csv), [run.json](results/english-term-fuzzy-auto/run.json)
- [한국어 term/fuzzy AUTO 추가 실험](results/korean-term-fuzzy-auto/): [summary.csv](results/korean-term-fuzzy-auto/summary.csv), [samples.csv](results/korean-term-fuzzy-auto/samples.csv), [run.json](results/korean-term-fuzzy-auto/run.json)
- [영어 이전/실패 이력](results/english-final/): 이전 전체 시도 산출물 및 [50k 요약](results/english-final/summary-50000.csv)
- [이전 README](README.temporary.md)

재현 명령(영어):

```bash
python3 benchmark.py \
  --corpus data/english/corpus.jsonl --queries data/english/queries.jsonl \
  --sizes 1000,10000,50000 --edits 0,1,2,3 \
  --grams 1,2,3,4,2-3,2-4 --samples 100 --repeats 1 \
  --hybrid --auto --es-ngram --oom-rss-mib 8192 \
  --max-method-seconds 180 --timeout 30 --output results/english-complete
```

추가 term/fuzzy AUTO variant만 재현하려면 `--sizes 50000 --repeats 3 --method-filter bm25_raw,bm25_oracle,fuzzy_auto_d1,fuzzy_auto_d2,term_auto_d1,term_d1,term_fuzzy_d1,term_fuzzy_auto_d1,term_suggest_fuzzy_auto_d1,term_suggest_fuzzy_auto_d2,term_parallel_fuzzy_bm25_auto_d1,parallel_fuzzy_auto_bm25_d1`를 지정하고 corpus/query 및 output 경로를 원하는 언어에 맞춰 바꾸세요.

`--max-method-seconds`는 개별 Python 후보색인 구축 및 method query 평가를 제한합니다. `samples.csv`와 summary의 sample 수/error 수로 부분 완료를 확인합니다. 100M corpus는 제공되어 있지 않아 실행하지 않았습니다.

## 실패 케이스 / 미완료 내역

영어 신규 run은 1k/10k/50k 모두 85/85 methods 완료, API 오류 0건, 제한으로 중단된 method 0건입니다(`results/english-complete/run.json`: `stopped_methods: []`). 따라서 신규 run 기준 **시간 초과/실행 중단 실패는 없습니다.** 다만 완료했더라도 아래 방법은 목적한 typo 검색에 실패하거나 지연이 지나치게 높았습니다.

| 실패/주의 방법 (영어 50k, typo_1) | 결과 | 실패 사유 |
|---|---:|---|
| ES n-gram direct d1 | Hit@10 0%, p95 1.40ms | 빠르지만 관련 문서를 검색하지 못함 |
| BM25 + ES n-gram parallel RRF d1 | Hit@10 0%, p95 1.74ms | n-gram branch에서 typo recall이 없고 raw BM25도 보완하지 못함 |
| Completion suggester | Hit@10 0%, p95 2.13ms | prefix 자동완성이라 typo correction이 아님 |
| Python unigram correction d1 | Hit@10 33%, p95 194.20ms | fuzzy d1 대비 Hit@10이 낮고 약 124배 느림 |
| Python bigram correction d1 | Hit@10 34%, p95 64.69ms | fuzzy d1과 비슷한 품질이나 약 41배 느림 |
| Python 2–3-gram correction d1 | Hit@10 34%, p95 84.40ms | fuzzy d1보다 낮은 Hit@10, 약 54배 느림 |
| fuzzy + ES n-gram parallel RRF d1 | Hit@10 36%, p95 2.95ms | fuzzy 단독과 품질 동일, p95는 약 1.9배 증가 |
| fuzzy + BM25 parallel RRF d1 | Hit@10 36%, p95 2.58ms | fuzzy 단독 대비 품질 향상 없이 p95 증가 |

비교 기준인 Elasticsearch fuzzy d1은 Hit@10 36%, p95 1.57ms였습니다. 배수는 각 방식 p95를 fuzzy d1 p95로 나눈 값이며, 이 실패/주의 분류는 이 합성 query와 단일 노드 설정에만 해당합니다. 이전 `results/english-final/` 실행에는 `ngram_2-3_d3`에서 **119 query 오류**(clean 28, typo_1 28, typo_2 27, typo_3 36)가 있었습니다. 이는 신규 run에서 재현되지 않았으며, 이전 오류 결과는 정상 성능 결과로 해석하면 안 됩니다.
