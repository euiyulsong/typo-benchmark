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

아래는 typo bucket별 correction accuracy와 검색 `MRR@10`, 클라이언트 전체 지연 p95입니다. p95는 밀리초이며, fuzzy는 교정 문자열을 반환하지 않으므로 accuracy는 N/A입니다. 각 bucket에는 50개 query × 3 repeats가 있습니다.

| 방법 | 1자 typo 정확도 / MRR | 2자 typo 정확도 / MRR | 3자 typo 정확도 / MRR | p95 (1자 / 2자 / 3자, ms) |
|---|---:|---:|---:|---:|
| BM25 raw | 0% / 0.00 | 0% / 0.00 | 0% / 0.00 | 1.96 / 1.93 / 1.91 |
| SymSpell d1 | 100% / 1.00 | 0% / 0.00 | 0% / 0.00 | 2.56 / 2.63 / 2.41 |
| SymSpell d2 | 100% / 1.00 | 100% / 1.00 | 2% / 0.02 | 2.37 / 2.27 / 2.21 |
| SymSpell d3 | 100% / 1.00 | 100% / 1.00 | 98% / 0.98 | 2.53 / 2.45 / 2.60 |
| Elasticsearch term d1 | 100% / 1.00 | 0% / 0.00 | 0% / 0.00 | 4.35 / 3.95 / 4.14 |
| Elasticsearch term d2 | 100% / 1.00 | 74% / 0.74 | 2% / 0.02 | 4.94 / 4.84 / 5.06 |
| Elasticsearch fuzzy d1 | N/A / 1.00 | N/A / 0.00 | N/A / 0.00 | 2.37 / 2.18 / 2.23 |
| Elasticsearch fuzzy d2 | N/A / 1.00 | N/A / 1.00 | N/A / 0.02 | 4.05 / 4.24 / 4.16 |
| Python bigram n-gram d2 | 100% / 1.00 | 100% / 1.00 | 2% / 0.02 | 3.48 / 3.57 / 3.27 |
| Python bigram n-gram d3 | 100% / 1.00 | 100% / 1.00 | 94% / 0.94 | 3.73 / 3.67 / 3.67 |

이번 합성 데이터 실험에서는 edit distance 3을 허용한 SymSpell이 세 글자 치환 오타에서 98% 정확도를 보였고, bigram n-gram은 94%였습니다. 1–2자 오류에서는 여러 d2 방법이 높은 정확도/MRR을 보였고, term suggester d2의 2자 오류 정확도는 74%였습니다. Unigram n-gram은 100,000문서에서 typo p95가 약 19.5–20.7ms로 길어 후보 폭증 영향을 드러냈습니다. 결과는 합성 영문 토큰 및 현재 구현/환경 기준이며, 한국어 또는 다른 코퍼스의 성능으로 일반화하면 안 됩니다.

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

매번 새 `typo-grid-*` 인덱스 생성. 기존 인덱스를 변경/삭제하지 않습니다. 종료 후 출력된 테스트 인덱스만 직접 삭제하세요. 인증은 ES_API_KEY 또는 ES_USER/ES_PASSWORD 환경변수로 설정합니다. TLS 인증서 검증은 켜져 있습니다.

## 방식

- bm25_raw: 입력 그대로 검색.
- bm25_oracle: 정답 쿼리로 검색하는 검색 품질 상한 baseline.
- symspell_d*: 메모리의 단어+문서 빈도 사전, CLOSEST 후보 중 빈도 최상위를 선택하고 BM25. 후보 recall은 최소 편집 거리 후보 집합 기준입니다.
- term_d*: ES term suggester 후보 -> 최상위 선택 -> BM25. 두 요청 지연을 합산합니다. d0은 후보 탐색을 생략하고 원문 검색합니다.
- fuzzy_d*: ES fuzzy match 직접 검색. 교정 문자열을 반환하지 않아 교정 정확도는 N/A.
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
- correction_accuracy: 교정 문자열 == clean 비율. 오류 요청 제외.
- false_correction_rate: 정상 입력을 잘못 변경한 비율. 정상 query가 있어야 계산됩니다.
- candidate_recall: 교정 후보에 정답 단어가 포함된 비율. 방식별 후보 집합 정의가 다릅니다.
- recall_at_k: 관련 문서 중 top-k로 검색한 비율.
- hit_at_k: top-k에 관련 문서가 하나 이상 있는 비율.
- mrr_at_k: 첫 관련 문서 순위의 역수. top-k 밖은 0.
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

정확도는 선택된 교정어가 clean term과 같은 비율이며, MRR@10은 관련 문서 순위를 평가합니다. 지연은 교정과 검색을 합친 클라이언트 p95(ms)입니다. `fuzzy`는 교정어를 반환하지 않으므로 정확도는 N/A입니다.

| 방법 | 1음절 치환 정확도 / MRR | 2음절 치환 정확도 / MRR | 3음절 치환 정확도 / MRR | p95 ms (1 / 2 / 3) |
|---|---:|---:|---:|---:|
| BM25 raw | 0% / 0.00 | 0% / 0.00 | 0% / 0.00 | 2.11 / 2.07 / 2.16 |
| SymSpell d1 | 67% / 0.40 | 0% / 0.00 | 0% / 0.00 | 2.71 / 2.47 / 2.57 |
| SymSpell d2 | 67% / 0.40 | 25% / 0.15 | 0% / 0.00 | 2.71 / 6.52 / 2.76 |
| SymSpell d3 | 67% / 0.40 | 25% / 0.15 | 8% / 0.06 | 2.85 / 6.76 / 73.06 |
| Elasticsearch term d2 | 76% / 0.45 | 19% / 0.11 | 0% / 0.00 | 6.25 / 6.41 / 6.08 |
| Elasticsearch fuzzy d1 | N/A / 0.45 | N/A / 0.00 | N/A / 0.00 | 3.55 / 3.36 / 3.36 |
| Elasticsearch fuzzy d2 | N/A / 0.42 | N/A / 0.21 | N/A / 0.00 | 6.12 / 6.12 / 5.74 |
| Python bigram n-gram d2 | 60% / 0.36 | 16% / 0.11 | 0% / 0.00 | 2.86 / 2.66 / 2.50 |

이 설정에서는 SymSpell이 d1에서도 정상 입력의 2%를 바꿨고, d2/d3에서는 5%를 바꿨습니다. 오타 평가에서 SymSpell 정답 후보 recall은 1자 95%, 2자 92%, d3의 3자 78%였지만, 후보를 frequency 우선으로 고르는 현재 구현의 최종 교정 정확도는 각각 67%, 25%, 8%였습니다. 즉 **후보에 정답이 포함되는 것과 정답을 최종 선택하는 것은 다릅니다.** d3의 긴 단어 lookup은 p95 73ms로 느려졌습니다. 이 실험 결과만으로 한국어 서비스에 SymSpell을 권장할 수 없으며, 세 방법 모두 실제 자연 오타용으로 검증되지 않았습니다.

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
