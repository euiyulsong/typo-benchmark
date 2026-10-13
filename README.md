# 오타 교정 + Elasticsearch BM25 비교

단일 토큰 오타 교정 방법과 Elasticsearch BM25 검색 품질/지연을 비교하는 재현 가능한 벤치마크입니다. 아래에는 실제 실행한 전체 그리드 결과를 요약했습니다.

## 실행 결과 (2026-10-11)

전체 결과는 [`results/summary.csv`](results/summary.csv), 요청별 상세 기록은 [`results/samples.csv`](results/samples.csv), 실행 파라미터는 [`results/run.json`](results/run.json)에 있습니다.

| 항목 | 값 |
|---|---:|
| Elasticsearch | 8.15.5, Docker 단일 노드 |
| 문서 수 | 1,000 / 10,000 / 100,000 |
| vocabulary | 최대 10,000개 영문 8자 토큰, seed=42 |
| 설정 | edits 0–3, grams 1/2/3/4/2-3/2-4, samples 50, repeats 3 |
| 평가 | 36개 method × 3개 corpus 크기, 총 432 summary 행 |
| 표본 / 오류 | 64,800 요청 기록 / 0 오류 |

### 100,000 문서에서 대표 결과

아래 표는 교정 문자열이 아니라 **최종 검색 결과**를 비교합니다. `MRR@10`은 첫 관련 문서의 순위를 반영하고, `Hit@10`은 top-10 안에 관련 문서가 하나 이상 있었던 query 비율입니다. p95는 교정이 있으면 교정+검색 전체 지연, fuzzy/raw BM25는 검색 지연입니다(밀리초). 각 typo bucket은 50개 query × 3 repeats입니다.

| 방법 | 1자 typo MRR / Hit@10 | 2자 typo MRR / Hit@10 | 3자 typo MRR / Hit@10 | p95 (1자 / 2자 / 3자, ms) |
|---|---:|---:|---:|---:|
| BM25 raw | 0.00 / 0% | 0.00 / 0% | 0.00 / 0% | 1.96 / 1.93 / 1.91 |
| SymSpell d1 | 1.00 / 100% | 0.00 / 0% | 0.00 / 0% | 2.56 / 2.63 / 2.41 |
| SymSpell d2 | 1.00 / 100% | 1.00 / 100% | 0.02 / 2% | 2.37 / 2.27 / 2.21 |
| SymSpell d3 | 1.00 / 100% | 1.00 / 100% | 0.98 / 98% | 2.53 / 2.45 / 2.60 |
| Elasticsearch term d1 | 1.00 / 100% | 0.00 / 0% | 0.00 / 0% | 4.35 / 3.95 / 4.14 |
| Elasticsearch term d2 | 1.00 / 100% | 0.74 / 74% | 0.02 / 2% | 4.94 / 4.84 / 5.06 |
| Elasticsearch fuzzy d1 | 1.00 / 100% | 0.00 / 0% | 0.00 / 0% | 2.37 / 2.18 / 2.23 |
| Elasticsearch fuzzy d2 | 1.00 / 100% | 1.00 / 100% | 0.02 / 2% | 4.05 / 4.24 / 4.16 |
| Python bigram n-gram d2 | 1.00 / 100% | 1.00 / 100% | 0.02 / 2% | 3.48 / 3.57 / 3.27 |
| Python bigram n-gram d3 | 1.00 / 100% | 1.00 / 100% | 0.94 / 94% | 3.73 / 3.67 / 3.67 |

검색 결과만 보면 이 합성 실험에서는 fuzzy d1이 1자 오류, fuzzy d2가 2자 오류에서 관련 문서를 top-10에 모두 넣었습니다. 3자 오류에서는 거의 찾지 못했습니다. SymSpell/ngram d3는 3자 오류를 더 많이 찾았지만 별도 후보 탐색 지연이 추가됩니다. Unigram n-gram은 100,000문서에서 typo p95가 약 17–18ms로 길었습니다. 이 결과는 합성 영문 토큰 및 현재 구현/환경 기준이며 다른 코퍼스 성능으로 일반화하면 안 됩니다.

## 실행

Python 3.10+와 실행 중인 Elasticsearch가 필요합니다.

```bash
pip install requests symspellpy rapidfuzz
python3 benchmark.py --url http://localhost:9200 \
  --sizes 1000,10000,100000 \
  --grams 1,2,3,4,2-3,2-4 --edits 0,1,2,3 \
  --samples 50 --repeats 3 --output results
```

작은 smoke run:

```bash
python3 benchmark.py --sizes 100 --vocab 100 --samples 5 --repeats 1 --grams 2,3 --edits 0,1
```

### Auto / completion / Elasticsearch n-gram / 스케일링 그리드

`--auto`는 Elasticsearch `fuzziness=AUTO`, `term` suggester `suggest_mode=always`(정상어도 후보로 바꿀 수 있어 false correction도 확인), 그리고 completion suggester(prefix completion)를 비교합니다. fuzzy/term/completion을 raw BM25 및 term→fuzzy와 함께 평가하고, `--hybrid`를 켜면 raw BM25와 해당 검색 결과의 RRF 병렬 조합도 추가합니다. Completion은 typo 교정기가 아니라 입력이 사전 prefix일 때 이어지는 토큰을 제안하는 방식이므로, typo 검색에선 후보 hit/검색 품질이 낮을 수 있습니다. prefix query 이외의 입력을 completion이 고치는 것으로 해석하지 마세요.

`--es-ngram`은 별도 2–3 character ngram analyzer 필드로 직접 검색합니다. `--hybrid`와 같이 쓰면 raw BM25+ngram(`parallel_es_ngram_bm25_d*`) 및 fuzzy+ngram(`parallel_fuzzy_es_ngram_d*`)을 병렬 실행해 RRF로 합칩니다. 기존 `ngram_*`은 Python 메모리 후보 교정 방식으로, 둘은 구현과 측정 범위가 다릅니다. completion 및 ngram의 추가 필드로 ES 색인 크기/색인 시간이 증가합니다.

대량 실행에서는 결과 폴더를 새 경로로 지정해 기존 결과를 덮어쓰지 말고, 완료 뒤 다음 스크립트로 특정 corpus 크기의 비교용 compact CSV를 만들 수 있습니다:

```bash
python3 summarize_results.py results/english-final/summary.csv --docs 50000 --output results/english-final/summary-50000.csv
```

단계적 corpus 크기 실험은 기존처럼 모든 단계에 같은 데이터 prefix를 사용하며, corpus 파일이 각 요청 크기보다 작으면 실제 크기까지만 진행합니다. `--max-method-seconds`는 과도하게 느린 방법을 건너뛰며, OOM guard는 benchmark 프로세스의 RSS를 확인합니다. Elasticsearch JVM/컨테이너 OOM은 별도 감시해야 합니다.

```bash
python3 benchmark.py --corpus large-corpus.jsonl --queries queries.jsonl \
  --sizes 1000,10000,100000,1000000,10000000,100000000 \
  --edits 0,1,2 --hybrid --auto --es-ngram \
  --samples 100 --repeats 3 --oom-rss-mib 8192 --max-method-seconds 300 --output results/scale
```

실험 종료 후 `summary.csv`는 MRR/Hit, correction/candidate 지표와 p50/p95/max, ES took, build/Python peak, ES index bytes/index time를 기록합니다. `--oom-rss-mib`는 프로세스 최대 RSS 기준이고 `--max-method-seconds`는 느린 method의 남은 query를 건너뜁니다. `samples.csv`는 query 단위 품질/지연/error를 보존합니다. ES heap/disk도 별도 모니터링하세요.

### 확장 기능 재실험 (2026-10-13)

기존 저장 corpus(영어 50k, 한국어 50k)로 확장 그리드를 재실행했습니다. 재현용 산출물은 [`results/english-final/`](results/english-final/) 및 [`results/korean-final/`](results/korean-final/)의 `summary.csv`, `samples.csv`, `run.json`, 50k 요약 CSV입니다. 전체 50k 단계에서 한국어 85개 method는 모두 완료, 영어는 time guard가 적용된 22개 method가 기록됐고 그중 `ngram_2-3_d3`만 일부 요청 실패/중단이 있어 상세 CSV의 error와 sample count를 확인해야 합니다. 저장소에 있는 corpus가 각 언어 50k이므로 1억 단계는 실행하지 않았습니다.

`--max-method-seconds`는 Python SymSpell/ngram처럼 corpus vocab에 따라 비용이 크게 증가하는 method의 구축과 query 평가를 제어합니다. 제한 시간 동안 method를 완료하지 못하면 건너뜁니다. method HTTP errors가 절반 이상이면 run을 중단합니다. 최종 재실행의 두 언어 모두 API 오류 0건이었습니다. 신규 옵션 그리드는 ES 8.15.5, 1 shard, 단일 노드, repeats=1이며 기존 2026-10-11 결과와 환경 및 반복 수가 다를 수 있습니다.

### 재실험 결과 메모 (50,000문서, typo_1)

아래 p95는 client end-to-end latency입니다. 샘플은 언어당 100 query입니다.

| 언어 | 방법 | Hit@10 | MRR@10 | p95 ms |
|---|---|---:|---:|---:|
| 한국어 | fuzzy d1 | 74% | 0.450 | 2.87 |
| 한국어 | ES ngram d1 | 0% | 0.000 | 1.27 |
| 한국어 | fuzzy + ES ngram 병렬 RRF d1 | 74% | 0.450 | 3.30 |
| 한국어 | Python bigram correction d1 | 53% | 0.361 | 1.70 |
| 한국어 | Python unigram correction d1 | 58% | 0.400 | 17.92 |
| 영어 | fuzzy d1 | 36% | 0.207 | 1.74 |
| 영어 | ES ngram d1 | 0% | 0.000 | 1.44 |

Fuzzy+ES-ngram 병렬 d1은 한국어에서 Hit/MRR이 fuzzy 단독과 같고 p95 3.30ms(단독 2.87ms)였습니다. 영어에서는 50k fuzzy+ngram 행이 제한 시간 때문에 미완료라 비교 가능한 점수로 보고하지 않습니다.

ES ngram 직접 검색은 이 단어 단위 합성 typo/qrel에서 관련 결과를 찾지 못했습니다. fuzzy+ngram 병렬은 fuzzy 단독 품질을 올리지 못하고 p95가 약 0.43ms 증가했습니다. 따라서 이 데이터에서는 fuzzy d1 단독이 병렬 fuzzy+ngram보다 단순하고 빠릅니다. 한국어 term `suggest_mode=always`는 clean query를 많이 잘못 바꾸어 clean Hit@10이 18%에 그쳤습니다.

영어는 50k 그리드에서 Python 후보 교정 계열의 일부가 45초/method 제한으로 생략되어 compact 결과 파일의 실제 범위를 확인하세요. 10k에서 Python unigram ngram은 typo_1 Hit@10 36.5%, p95 69.6ms였고, ES ngram direct는 Hit 0%, p95 약 1.4ms였습니다. 이 두 구현은 후보 교정과 직접 ngram 검색으로 동작이 다르며, 결과는 합성 query 기준입니다.

매번 새 `typo-grid-*` 인덱스 생성. 기존 인덱스를 변경/삭제하지 않습니다. 종료 후 출력된 테스트 인덱스만 직접 삭제하세요. 인증은 ES_API_KEY 또는 ES_USER/ES_PASSWORD 환경변수로 설정합니다. TLS 인증서 검증은 켜져 있습니다.

## 방식

- bm25_raw: 입력 그대로 검색.
- bm25_oracle: 정답 쿼리로 검색하는 검색 품질 상한 baseline.
- symspell_d*: 메모리의 단어+문서 빈도 사전, CLOSEST 후보 중 빈도 최상위를 선택하고 BM25. 품질은 다른 방식과 동일하게 검색 MRR/Hit으로 비교합니다.
- term_d*: ES term suggester 후보 -> 최상위 선택 -> BM25. 두 요청 지연을 합산합니다. d0은 후보 탐색을 생략하고 원문 검색합니다.
- fuzzy_d*: ES fuzzy match로 문서를 직접 검색. 검색 MRR/Hit이 주 품질 지표입니다.
- ngram_*_d*: 문자 gram -> term 집합의 **Python 메모리 역색인**에서 후보 생성 -> Dice 유사도로 최대 candidate-limit개 선택 -> OSA 거리 필터 -> 거리 최소/문서 빈도 최대 후보 -> BM25.

`2-3`은 문자 bigram+trigram을 함께 사용합니다. n-gram 후보색인은 ES ngram 필드가 아닙니다. 토큰 후보 교정의 gram 크기를 비교하기 위한 별도 메모리 구현입니다. ES 문자 ngram 문서 검색과 직접 비교하는 실험은 포함하지 않습니다.

ES fuzzy/term은 최대 편집 거리 2까지 지원하므로 d3 행은 생성하지 않습니다. SymSpell/ngram은 3까지 비교합니다. 거리 지표는 인접 문자 교환을 포함하는 OSA 계열입니다. ES와 SymSpell의 후보 제한, prefix, 정렬/정규화 방식이 완전히 같지는 않습니다.

## 데이터

기본 데이터는 seed=42의 영문 8자 토큰으로 생성합니다. clean 및 1/2/3글자 치환 오타를 각각 평가합니다. 한국어 성능을 대표하지 않으며 삽입/삭제/교환/띄어쓰기/키보드 오타 분포를 대표하지도 않습니다.

실제 corpus와 사람이 확인한 query/qrels를 함께 제공할 수 있습니다:

corpus.jsonl:
```json
{"id":"1","content":"카카오페이 결제 취소 방법"}
{"id":"2","content":"카카오페이 환불 안내"}
{"id":"3","content":"삼성전자 제품 안내"}
```
queries.jsonl:
```json
{"clean":"카카오페이","typo":"카카오패이","relevant_ids":["1","2"]}
{"clean":"카카오페이","typo":"카카오페이","relevant_ids":["1","2"]}
```

```bash
python3 benchmark.py --corpus corpus.jsonl --queries queries.jsonl --sizes 1000,10000,100000
```

clean/typo는 각각 단일 whitespace 토큰이어야 합니다. 멀티턴/문장 문맥 교정 실험은 아닙니다. 실제 데이터에는 정상 단어, 고유명사, 숫자/코드와 여러 오타 유형을 포함하세요. qrels는 검색 관련 문서 ID로 지정합니다. 아직 색인되지 않은 문서는 qrels에서 제외하며 관련 문서가 없는 query는 해당 단계에서 제외합니다. corpus 끝에 도달하면 같은 크기를 재측정하지 않습니다.

## 지표

summary.csv:
- correction_accuracy: 교정 문자열 == clean 비율. 검색 결과 품질이 아니라 교정 방식의 진단 지표이며 fuzzy에는 해당하지 않습니다.
- false_correction_rate: 정상 입력을 잘못 변경한 비율. 검색 결과가 아니라 교정 문자열을 바꾸는 방법에만 해당합니다.
- candidate_recall: 교정 후보에 정답 단어가 포함된 비율. 최종 검색 결과가 아니고 방식별 후보 집합 정의가 다릅니다.
- recall_at_k: 관련 문서 중 top-k로 검색한 비율.
- hit_at_k: top-k에 관련 문서가 하나 이상 있는 비율.
- mrr_at_k: 첫 관련 문서 순위의 역수. top-k 밖은 0. 교정 여부와 무관하게 모든 방법의 최종 검색 결과를 비교하는 주 품질 지표입니다.
- p50/p95/max_ms: 교정+검색의 클라이언트 전체 지연.
- correction_p95_ms: 후보 생성과 선택 지연. term은 첫 ES 요청 왕복 포함.
- es_took_p95_ms: ES가 반환한 took 합계, 네트워크/클라이언트 제외.
- build_seconds/python_peak_mib: 로컬 교정 사전 구축 시간 및 tracemalloc peak. native 메모리/RSS와 ES heap은 제외. 공유 vocabulary 사전도 제외.
- index_bytes/index_seconds: 공통 BM25 ES 색인 크기와 누적 indexing+refresh 시간. 방식별 추가 ES 색인은 없습니다.
- errors: 실패 수. 실패를 지연 percentile에서 제외하므로 반드시 같이 봐야 합니다.

samples.csv는 요청별 기록이고 run.json은 설정과 테스트 인덱스 이름을 보존합니다. repeats의 같은 query 반복은 독립적인 품질 표본이 아닙니다.

## 해석

느려졌다는 이유로 조기 종료하지 않습니다. 오류/timeout은 기록하고 다음 query로 진행합니다. p95와 교정 정확도, MRR을 함께 비교하세요. 기본 10초 timeout은 요청 단위이며 전체 실험 종료 시간 제한은 아닙니다.

1 shard / whitespace analyzer / top-k / 순차 요청 / warm cache에 가까운 측정입니다. 실제 배포 analyzer, shard 구성, 동시 요청 수가 달라지면 결과가 달라집니다. request cache는 끄지만 OS page cache는 비우지 않습니다. 색인 직후 merge 등 background 작업에 따른 잡음이 생길 수 있습니다.

ngram 구현은 전체 후보 overlap을 수집/정렬하므로 흔한 unigram에서 후보 폭증과 비용이 나타날 수 있습니다. 이 Python 구현과 native SymSpell 또는 ES 서버의 지연 차이를 알고리즘 자체의 우열로 단정하지 마세요.

문서 수와 함께 vocab 열을 보세요. 고정 어휘에 문서만 늘리는 경우와 새 어휘까지 늘어나는 경우의 후보 탐색 비용은 다릅니다. 기본 vocab을 달리해 별도 실행하거나 실제 corpus를 이용하세요.

한국어는 완성형 음절 단위 character distance입니다. 자모 분해나 두벌식 키 입력 기준 거리 실험은 포함하지 않습니다.

## 한국어 평가: KLUE-YNAT 뉴스 제목

한국어 공개 데이터로 추가 평가했습니다. 원본은 [KLUE](https://github.com/KLUE-benchmark/KLUE)의 YNAT 뉴스 제목 데이터이며, Hugging Face의 [`klue/klue`, `ynat`](https://huggingface.co/datasets/klue/klue)에서 가져왔습니다. 데이터셋 라이선스는 **CC-BY-SA-4.0**입니다. 이 저장소에는 KLUE 원문을 재배포하지 않고, 다운로드/변환 스크립트와 평가 결과만 포함합니다.

실행 조건: train 뒤 validation에서 비어 있지 않은 제목 50,000개를 사용하고, 제목에 2회 이상 등장한 3음절 이상 한글 토큰에서 seed=42로 100개를 뽑았습니다. 각 토큰에 대해 정상어와 한글 완성형 음절을 무작위 치환한 1/2/3자 오타를 만들었습니다. 검색 관련 문서는 정답 토큰이 등장한 첫 문서로 지정했습니다. 이 방식은 **합성 음절 치환 실험**이지 실제 한국어 입력 오타 평가가 아닙니다. 띄어쓰기, 자모 오입력, 두벌식 인접키, 형태소/조사 오류를 반영하지 않으며, 단어 빈도 필터가 흔한 토큰 위주 표본을 만듭니다.

재현:

```bash
pip install datasets requests symspellpy rapidfuzz
python3 korean_eval.py --output data/korean --max-docs 50000 --queries 100 --min-frequency 2 --seed 42
python3 benchmark.py \
  --corpus data/korean/corpus.jsonl --queries data/korean/queries.jsonl \
  --sizes 1000,10000,50000 --edits 0,1,2,3 \
  --grams 1,2,3,4,2-3,2-4 --samples 100 --repeats 3 \
  --output results/korean
```

실행 파일: [`korean_eval.py`](korean_eval.py), 생성 데이터 메타데이터: [`results/korean/dataset.json`](results/korean/dataset.json), 전체 지표: [`results/korean/summary.csv`](results/korean/summary.csv), 요청별 로그: [`results/korean/samples.csv`](results/korean/samples.csv), 설정: [`results/korean/run.json`](results/korean/run.json). 한국어 실험은 최대 50,000문서까지만 진행했습니다. 1,000문서 단계에서는 관련 정답이 있는 clean query가 13개(오타 bucket별 39건), 10,000문서에서는 clean query 55개(오타 bucket별 165건), 50,000문서에서 clean query 100개(오타 bucket별 300건, 각 100 query × 3 repeats)였습니다. 전체 432 summary 행에서 요청 오류는 0건입니다.

### 한국어 결과 (50,000문서)

아래는 전부 교정어 정확도가 아니라 **최종 검색 결과 품질**입니다. `MRR@10`은 첫 관련 문서의 순위, `Hit@10`은 top-10 안의 관련 문서 존재율입니다. p95는 교정+검색 전체의 클라이언트 지연(ms)이며, fuzzy는 문서를 직접 검색하므로 검색 요청 지연입니다. clean 검색 기준선의 BM25 raw MRR/Hit@10은 0.56/81%입니다.

| 방법 | 정상어 MRR / Hit@10 | 1음절 오타 MRR / Hit@10 | 2음절 오타 MRR / Hit@10 | 3음절 오타 MRR / Hit@10 | p95 ms (1 / 2 / 3) |
|---|---:|---:|---:|---:|---:|
| BM25 raw | 0.56 / 81% | 0.00 / 0% | 0.00 / 0% | 0.00 / 0% | 2.37 / 2.45 / 2.39 |
| BM25 oracle | 0.56 / 81% | 0.56 / 81% | 0.56 / 81% | 0.56 / 81% | 2.52 / 2.62 / 2.48 |
| SymSpell d1 | 0.56 / 81% | 0.40 / 58% | 0.00 / 0% | 0.00 / 0% | 2.50 / 2.26 / 2.22 |
| SymSpell d2 | 0.56 / 81% | 0.40 / 58% | 0.15 / 23% | 0.00 / 0% | 2.94 / 7.41 / 2.82 |
| SymSpell d3 | 0.56 / 81% | 0.40 / 58% | 0.15 / 23% | 0.06 / 8% | 2.94 / 6.80 / 73.12 |
| Elasticsearch term d1 | 0.56 / 81% | 0.45 / 66% | 0.00 / 0% | 0.00 / 0% | 5.48 / 5.07 / 5.20 |
| Elasticsearch term d2 | 0.56 / 81% | 0.45 / 66% | 0.11 / 18% | 0.00 / 0% | 6.28 / 6.34 / 6.00 |
| Elasticsearch fuzzy d1 | 0.55 / 82% | 0.45 / 74% | 0.00 / 0% | 0.00 / 0% | 4.08 / 3.88 / 3.85 |
| Elasticsearch fuzzy d2 | 0.54 / 79% | 0.42 / 75% | 0.21 / 36% | 0.00 / 0% | 6.47 / 6.22 / 5.90 |
| Python bigram n-gram d2 | 0.56 / 81% | 0.36 / 53% | 0.11 / 16% | 0.00 / 0% | 2.90 / 2.70 / 2.48 |

이 비교에서는 fuzzy d1이 1음절 오타의 Hit@10 74%, fuzzy d2가 2음절 오타의 Hit@10 36%를 기록해 표에 포함된 방법 중 가장 높았습니다. 3음절 합성 오타는 어느 방법도 유의미하게 찾지 못했습니다. SymSpell은 d2의 2음절 오타에서 Hit@10 23%였고 d3의 3음절 오타에서는 8%였으며 p95가 73ms까지 치솟았습니다. 다만 실제 오타 유형이 아닌 무작위 음절 치환과 희소한 qrels 기준 결과이므로 실제 서비스 성능이나 방법의 일반적 우위를 의미하지 않습니다. 후보 recall과 correction accuracy는 진단용 보조 지표로 CSV에 유지하되, 모든 방법의 주 비교는 공통 검색 지표인 MRR/Hit입니다.

샘플 후보/교정 사례 (SymSpell d2, 동일한 세팅의 요청별 CSV에서 발췌):

| 정답 | 합성 입력 | 선택 교정어 | 정답이 후보에 포함 |
|---|---|---|---|
| `회원수` | `회셆수` | `회수` | 예 |
| `이용객` | `션갺객` | `관광객` | 예 |
| `나전칠기` | `붿전퓏기` | `전투기` | 예 |

오류 문자가 무작위 한글 음절이라 자연스러운 오타가 아닙니다. 예시와 점수는 방법의 한국어 우열을 확정하지 않으며, 실제 query typo/qrels로 다시 측정해야 합니다.

### 출처 및 라이선스

- KLUE Benchmark: https://github.com/KLUE-benchmark/KLUE
- Hugging Face dataset card: https://huggingface.co/datasets/klue/klue
- 데이터셋 라이선스: CC-BY-SA-4.0. 데이터 사용 시 원 저작물의 라이선스와 attribution 조건을 따르세요.
- 논문: Park et al., [KLUE: Korean Language Understanding Evaluation](https://arxiv.org/abs/2105.09680), 2021.

## 요청된 조합 실험: clean/typo × raw/fuzzy/parallel/hybrid

`benchmark.py --hybrid`는 다음 결과를 추가합니다.

- `parallel_fuzzy_bm25_d1/d2`: 입력 원문으로 BM25와 fuzzy BM25를 동시에 요청하고, 두 결과를 Reciprocal Rank Fusion(RRF, 상수 60)으로 결합합니다.
- `term_d1/d2`: Elasticsearch term suggester의 첫 후보로 BM25 검색합니다.
- `term_bm25_d1/d2`: term suggester로 입력을 교정한 뒤 일반 BM25로 검색합니다. `term_d*`의 명시적 비교군입니다.
- `fuzzy_d1/d2`: fuzzy match로 직접 검색합니다.
- `bm25_raw`: 입력 그대로의 BM25 검색. `clean` bucket은 오타 없는 query, `typo_1/2/3` bucket은 오타 query를 측정합니다.

`term suggest 후 fuzzy` 실험은 suggestion 후보를 fuzzy 검색에 넣는 `term_fuzzy_d1/d2`로 기록합니다. 먼저 suggester 후보를 얻고 그 후보 문자열을 fuzzy query로 검색하며 두 ES 요청 시간을 함께 기록합니다. `term suggest 후 fuzzy+BM25 병렬`은 `term_parallel_fuzzy_bm25_d1/d2`이며, suggestion 이후 선택된 후보로 fuzzy와 일반 BM25를 병렬 실행하고 RRF 결합합니다. `--hybrid`에서 세 추가 방법이 함께 활성화됩니다.

`term_d*` 기존 결과는 suggestion 단계에서 후보를 선택한 다음 raw BM25로 검색하는 방식입니다. `term_bm25_d*`는 동일한 순서를 명시적인 신규 method로 기록하여 term→BM25를 다른 조합과 직접 비교할 수 있도록 합니다.

### 공개 영어 데이터: AG News

영어는 Hugging Face의 [`fancyzhx/ag_news`](https://huggingface.co/datasets/fancyzhx/ag_news) 공개 뉴스 데이터의 train/test 본문을 받아 동일한 clean, 1/2/3자 합성 치환 오타 query를 생성합니다. upstream 데이터 카드의 라이선스는 MIT입니다. 문서는 원문 텍스트를 corpus로 만들고, 각 query의 qrel은 정답 토큰이 처음 나타나는 문서입니다. 따라서 자연발생 오타의 현실성을 평가하는 실험은 아닙니다.

```bash
pip install datasets requests symspellpy rapidfuzz
python3 english_eval.py --output data/english --max-docs 50000 --queries 100 --min-frequency 2 --seed 42
python3 benchmark.py --corpus data/english/corpus.jsonl --queries data/english/queries.jsonl \
  --sizes 1000,10000,50000 --edits 0,1,2 --samples 100 --repeats 3 \
  --hybrid --output results/english
```

한국어도 같은 검색 조합은 `--hybrid`를 붙여 실행합니다.

```bash
python3 benchmark.py --corpus data/korean/corpus.jsonl --queries data/korean/queries.jsonl \
  --sizes 1000,10000,50000 --edits 0,1,2 --samples 100 --repeats 3 \
  --hybrid --output results/korean-hybrid
```

출력의 `summary.csv`는 clean/typo bucket별 최종 검색 MRR/Hit@10과 지연을 기록하고, `samples.csv`는 query 단위 결과를 보존합니다. `parallel_fuzzy_bm25`의 `es_took_ms`는 두 서버 took의 합계이며 클라이언트 latency에는 실제 병렬 왕복이 반영됩니다. 실행 전 Elasticsearch가 켜져 있어야 합니다.

### 실행 결과 (2026-10-12, 50,000문서, seed=42)

KLUE-YNAT 한국어와 AG News 영어 각각 100개 query term을 clean 및 1/2/3자 치환 typo로 만들고, repeats=1로 요청된 검색군을 비교했습니다. 아래는 100개 표본이 있는 clean/typo_1/typo_2 각 bucket의 **MRR@10 / Hit@10과 p95 end-to-end 지연(ms)**입니다. typo_3 및 모든 상세 값은 결과 CSV에 있습니다. 오류는 두 데이터셋 모두 0건입니다.

| 데이터/입력 | 방법 | MRR@10 / Hit@10 | p95 지연(ms) |
|---|---|---:|---:|
| 한국어 clean | BM25 raw | 0.556 / 81% | 2.01 |
| 한국어 clean | term→BM25 d1 | 0.556 / 81% | 3.57 |
| 한국어 clean | term→BM25 d2 | 0.556 / 81% | 3.45 |
| 한국어 clean | fuzzy d1 | 0.545 / 82% | 2.79 |
| 한국어 clean | fuzzy d2 | 0.536 / 79% | 5.27 |
| 한국어 clean | 병렬 fuzzy+BM25 d1 | 0.561 / 82% | 3.62 |
| 한국어 clean | 병렬 fuzzy+BM25 d2 | 0.557 / 79% | 6.35 |
| 한국어 clean | term→fuzzy d1 | 0.545 / 82% | 4.42 |
| 한국어 clean | term→fuzzy d2 | 0.536 / 79% | 6.57 |
| 한국어 clean | term→병렬 결합 d1 | 0.561 / 82% | 5.77 |
| 한국어 clean | term→병렬 결합 d2 | 0.557 / 79% | 8.35 |
| 한국어 typo_1 | BM25 raw | 0.000 / 0% | 1.95 |
| 한국어 typo_1 | term→BM25 d1 | 0.448 / 66% | 4.21 |
| 한국어 typo_1 | term→BM25 d2 | 0.448 / 66% | 4.59 |
| 한국어 typo_1 | fuzzy d1 | 0.450 / 74% | 3.00 |
| 한국어 typo_1 | fuzzy d2 | 0.419 / 75% | 5.08 |
| 한국어 typo_1 | 병렬 fuzzy+BM25 d1 | 0.450 / 74% | 3.68 |
| 한국어 typo_1 | 병렬 fuzzy+BM25 d2 | 0.419 / 75% | 6.15 |
| 한국어 typo_1 | term→fuzzy d1 | 0.453 / 71% | 4.92 |
| 한국어 typo_1 | term→fuzzy d2 | 0.444 / 69% | 8.17 |
| 한국어 typo_1 | term→병렬 결합 d1 | 0.462 / 71% | 6.32 |
| 한국어 typo_1 | term→병렬 결합 d2 | 0.459 / 69% | 9.50 |
| 한국어 typo_2 | BM25 raw | 0.000 / 0% | 2.05 |
| 한국어 typo_2 | term→BM25 d1 | 0.000 / 0% | 4.03 |
| 한국어 typo_2 | term→BM25 d2 | 0.107 / 18% | 4.28 |
| 한국어 typo_2 | fuzzy d1 | 0.000 / 0% | 2.61 |
| 한국어 typo_2 | fuzzy d2 | 0.208 / 36% | 4.96 |
| 한국어 typo_2 | 병렬 fuzzy+BM25 d1 | 0.000 / 0% | 3.22 |
| 한국어 typo_2 | 병렬 fuzzy+BM25 d2 | 0.208 / 36% | 5.87 |
| 한국어 typo_2 | term→fuzzy d1 | 0.000 / 0% | 4.66 |
| 한국어 typo_2 | term→fuzzy d2 | 0.218 / 35% | 7.97 |
| 한국어 typo_2 | term→병렬 결합 d1 | 0.000 / 0% | 5.98 |
| 한국어 typo_2 | term→병렬 결합 d2 | 0.221 / 35% | 9.11 |
| 영어 clean | BM25 raw | 0.219 / 39% | 1.97 |
| 영어 clean | term→BM25 d1 | 0.322 / 54% | 4.06 |
| 영어 clean | term→BM25 d2 | 0.322 / 54% | 3.53 |
| 영어 clean | fuzzy d1 | 0.252 / 50% | 3.01 |
| 영어 clean | fuzzy d2 | 0.170 / 31% | 4.00 |
| 영어 clean | 병렬 fuzzy+BM25 d1 | 0.326 / 59% | 4.38 |
| 영어 clean | 병렬 fuzzy+BM25 d2 | 0.269 / 50% | 4.77 |
| 영어 clean | term→fuzzy d1 | 0.236 / 51% | 3.93 |
| 영어 clean | term→fuzzy d2 | 0.186 / 34% | 5.86 |
| 영어 clean | term→병렬 결합 d1 | 0.324 / 60% | 4.58 |
| 영어 clean | term→병렬 결합 d2 | 0.291 / 54% | 6.54 |
| 영어 typo_1 | BM25 raw | 0.000 / 0% | 1.72 |
| 영어 typo_1 | term→BM25 d1 | 0.191 / 34% | 4.47 |
| 영어 typo_1 | term→BM25 d2 | 0.193 / 35% | 4.18 |
| 영어 typo_1 | fuzzy d1 | 0.207 / 36% | 2.87 |
| 영어 typo_1 | fuzzy d2 | 0.172 / 36% | 4.02 |
| 영어 typo_1 | 병렬 fuzzy+BM25 d1 | 0.207 / 36% | 4.07 |
| 영어 typo_1 | 병렬 fuzzy+BM25 d2 | 0.172 / 36% | 4.67 |
| 영어 typo_1 | term→fuzzy d1 | 0.169 / 36% | 4.13 |
| 영어 typo_1 | term→fuzzy d2 | 0.135 / 25% | 5.98 |
| 영어 typo_1 | term→병렬 결합 d1 | 0.203 / 41% | 4.97 |
| 영어 typo_1 | term→병렬 결합 d2 | 0.203 / 39% | 7.47 |
| 영어 typo_2 | BM25 raw | 0.000 / 0% | 1.75 |
| 영어 typo_2 | term→BM25 d1 | 0.000 / 0% | 4.43 |
| 영어 typo_2 | term→BM25 d2 | 0.076 / 14% | 4.28 |
| 영어 typo_2 | fuzzy d1 | 0.000 / 0% | 2.69 |
| 영어 typo_2 | fuzzy d2 | 0.124 / 26% | 3.86 |
| 영어 typo_2 | 병렬 fuzzy+BM25 d1 | 0.000 / 0% | 4.34 |
| 영어 typo_2 | 병렬 fuzzy+BM25 d2 | 0.124 / 26% | 4.75 |
| 영어 typo_2 | term→fuzzy d1 | 0.000 / 0% | 4.28 |
| 영어 typo_2 | term→fuzzy d2 | 0.107 / 20% | 6.04 |
| 영어 typo_2 | term→병렬 결합 d1 | 0.000 / 0% | 4.93 |
| 영어 typo_2 | term→병렬 결합 d2 | 0.125 / 22% | 7.03 |

기본 term suggester의 단독 결과는 `term_d1/d2` 행을, clean/typo_1/2/3 전체 검색 결과는 전체 summary에서 확인할 수 있습니다. typo_3는 3자 무작위 치환입니다. 합성 오타 방식, 첫 등장 문서 하나만 qrel로 쓰는 방식, AG News query 후보의 단어 빈도 분포가 지표에 영향을 줍니다. 재현용 산출물: `results/korean-hybrid/{summary.csv,samples.csv,run.json}`, `results/english/{summary.csv,samples.csv,run.json}`. 데이터셋 메타데이터는 각 폴더의 `dataset.json`에 있습니다.

### 결과 분석 및 선택 기준

**한 가지 방법이 모든 상황에서 가장 좋지는 않습니다.** 검색 품질, 지연, 정상 입력에 대한 보수성, 데이터셋 간 일관성을 같이 보면 다음처럼 해석할 수 있습니다.

- **오타 없는 입력이 대부분이면 raw BM25를 기본으로 권장합니다.** 한국어 clean에서는 BM25 raw가 MRR 0.556 / Hit 81%로 이미 강하고, fuzzy d1은 Hit을 82%로 거의 바꾸지 않으면서 p95 지연이 2.01ms에서 2.79ms로 늘었습니다. 영어에서는 병렬 fuzzy+BM25 d1이 clean Hit을 39%에서 59%로 올렸지만, typo 생성 실험으로 만들어진 표본이고 p95는 1.97ms에서 4.38ms로 증가했습니다. 따라서 영어 결과만으로 항상 fuzzy를 켜는 결정을 내리기보다, 실제 서비스 clean query의 Hit/MRR과 지연 예산으로 검증하는 편이 합리적입니다.
- **1자 오타 대응을 우선하면 fuzzy d1이 단순하고 효과적인 선택입니다.** 한국어 typo_1 Hit은 74%, 영어는 36%였습니다. raw BM25는 두 언어 모두 이 합성 오타에서 Hit 0%였습니다. fuzzy d2는 d1보다 오류 허용 범위는 넓지만 1자 typo 품질을 일관되게 개선하지 못하고 비용이 더 들었습니다. 오타 허용은 실제 오타 가능성이 있는 입력에만 적용하거나, 엄격한 지연 예산 아래 d1부터 검증하는 방식을 권합니다.
- **2자 오타가 중요하면 d2가 필요하지만 성공률은 여전히 제한적입니다.** fuzzy d2의 typo_2 Hit은 한국어 36%, 영어 26%였습니다. term suggest→fuzzy+BM25 결합은 각각 35%, 22%로 이 표본에서는 fuzzy d2 단독보다 낫지 않았고, p95도 더 길었습니다(한국어 약 9.11ms, 영어 약 7.03ms). 이 방법을 기본값으로 삼기보다 typo_2 입력 비율이 높은 경우에 한해 추가 이득이 실제로 있는지 측정해야 합니다.
- **BM25와 fuzzy 병렬 결합은 언어별 효과가 다릅니다.** 한국어 typo 검색에서는 RRF 결합이 fuzzy 단독보다 MRR/Hit을 개선하지 않았습니다. 영어 clean에서는 d1 결합이 상대적으로 높은 Hit(59%)을 보였고 typo_1에서는 suggestion 후 결합이 Hit 41%로 fuzzy 단독 36%보다 높았지만, 지연은 더 컸습니다. 영어 clean의 향상은 관련 문서가 처음 나온 문서 하나만 qrel로 둔 실험 조건과 데이터 특성에 영향을 받을 수 있으므로 실제 관련성 판단이 있는 평가로 확인해야 합니다.
- **term suggester는 이번 설정에서 단독 기본 검색으로 우위가 없었습니다.** 명시적 term→BM25 실험의 typo_1 Hit은 한국어 66%, 영어 34%로 fuzzy d1(각 74%, 36%)보다 낮았습니다. clean query를 후보 제안으로 잘못 바꾼 비율(`false_correction_rate`)도 한국어 term d1/d2에서 2%/5%, 영어에서 30%/33%였습니다. 영어 vocabulary에 희귀 토큰과 뉴스 고유명사가 섞인 점 때문에 특히 과잉 교정에 취약했을 수 있습니다. 정상 입력을 그대로 보존해야 한다면 suggester 후보를 무조건 적용하지 말고, 원문 결과와 후보 결과를 비교하거나 confidence/빈도 임계값을 둬야 합니다.
- **3자 합성 오타는 이 실험의 어떤 fuzzy/term 조합도 해결하지 못했습니다.** 두 언어에서 관련 결과가 사실상 검색되지 않았습니다. 더 큰 편집거리로 무작정 확장하기보다는 별도 오타 사전, 언어별 교정기, prefix/ngram 후보 생성 등을 실제 쿼리 로그로 비교해야 합니다.

**실무 출발점:** clean 성능과 낮은 지연이 우선이면 BM25 raw를 유지하고, 오타 대응이 요구되면 fuzzy d1을 추가 비교군으로 시작합니다. 영어처럼 clean query에서도 병렬 결합 향상이 보이는 경우에는 실제 qrels와 p95/p99 지연 예산으로 효과를 확인한 후 적용 여부를 정합니다. term suggester 조합은 잘못된 clean 수정률을 낮추는 정책을 마련하고 나서 평가하는 편이 좋습니다. 현재 숫자는 언어별 100 query 단어, 단일 합성 오타 유형, 한 문서 qrel, 단일 ES 환경의 탐색 결과입니다. 대표 성능이나 통계적 유의성을 주장하지 않으며, 실제 검색 로그 기반 query와 사람이 검증한 다중 qrels, 여러 repeats를 이용한 재평가가 필요합니다.

#### 단일 방법을 위한 단순 평균 비교

한 방법만 선택하는 판단을 돕기 위해 각 언어에서 clean, typo_1, typo_2, typo_3의 Hit@10을 동일 가중치로 평균하고, 두 언어 평균도 동일 가중치로 계산했습니다. 따라서 이 값은 실제 트래픽 비율을 반영한 운영 점수가 아니라 typo 비율을 모르는 상태에서의 **균등 시나리오 평균**입니다. 결과 파일의 표본 수는 bucket별 100 query이며, 언어별 같은 query term이 clean/typo bucket에 반복되므로 이를 통계적 독립 표본으로 해석하면 안 됩니다.

| 단일 검색 방법 | 한국어 평균 Hit@10 / p95(ms) | 영어 평균 Hit@10 / p95(ms) | 전체 평균 Hit@10 / MRR@10 |
|---|---:|---:|---:|
| BM25 raw | 20.2% / 1.70 | 9.8% / 5.30 | 15.0% / 0.097 |
| term→BM25 d1 | 36.8% / 3.94 | 22.0% / 4.30 | 29.4% / 0.190 |
| term→BM25 d2 | 41.2% / 4.09 | 25.8% / 4.01 | **33.5% / 0.213** |
| Fuzzy d1 | 39.0% / 2.43 | 21.5% / 2.82 | 30.2% / 0.182 |
| Fuzzy d2 | **47.5%** / 4.79 | 23.2% / 6.77 | **35.4% / 0.204** |
| Parallel fuzzy+BM25 d1 (RRF) | 39.0% / 3.35 | 23.8% / 3.58 | 31.4% / 0.193 |
| Term suggest → fuzzy d1 | 38.2% / 4.39 | 21.8% / 10.40 | 30.0% / 0.175 |
| Term suggest → parallel fuzzy+BM25 d1 (RRF) | 38.2% / 5.41 | **25.2%** / 5.13 | 31.8% / 0.194 |

위의 명시적 term→BM25 실험 결과를 포함해 다시 계산하면 **bucket·언어를 균등 가중한 평균 Hit@10은 fuzzy d2가 가장 높고(35.4%), 평균 MRR@10은 term→BM25 d2가 가장 높습니다(0.213).** Hit@10과 MRR@10이 서로 다른 방법을 1위로 가리키므로 단일 지표로 확정적인 승자를 정할 수 없습니다. 오타 복원율/상위순위를 함께 보는 품질 중심의 단일 선택은 `term_bm25_d2`가 유력합니다(Hit 평균 33.5%, MRR 평균 0.213, 언어별 평균 p95 약 4.05ms). 다만 이 선택은 term suggester가 clean query를 잘못 바꾸는 위험을 포함하며, p95가 BM25 raw보다 높습니다. 과잉 교정 위험과 지연을 더 중시하면 fuzzy d1이 보수적인 대안입니다. 평균은 clean/오타 bucket과 두 언어에 각각 같은 비중을 준 것이므로, 실제 query 비율로 가중치를 바꾸면 결론도 바뀔 수 있습니다. 각 bucket 100개, repeats=1의 합성 데이터 결과이므로 작은 점수 차이를 통계적으로 확정된 우위로 해석하지 않습니다.
