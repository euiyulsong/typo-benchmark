#!/usr/bin/env python3
"""Single-token typo correction + Elasticsearch BM25 quality/latency grid.
Dependencies: requests symspellpy rapidfuzz. See README.md.
"""
import argparse, csv, json, math, os, random, statistics, time, tracemalloc, uuid
from collections import Counter, defaultdict
from pathlib import Path
import requests
from rapidfuzz.distance import OSA
from symspellpy import SymSpell, Verbosity


def pct(xs, p):
    return sorted(xs)[max(0, math.ceil(len(xs)*p)-1)] if xs else None


def grams(word, ns):
    return {word[i:i+n] for n in ns for i in range(len(word)-n+1)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://localhost:9200')
    p.add_argument('--sizes', default='1000,10000,100000')
    p.add_argument('--edits', default='0,1,2,3')
    p.add_argument('--grams', default='1,2,3,4,2-3,2-4')
    p.add_argument('--samples', type=int, default=100)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--candidate-limit', type=int, default=100)
    p.add_argument('--k', type=int, default=10)
    p.add_argument('--vocab', type=int, default=10000)
    p.add_argument('--words', type=int, default=30)
    p.add_argument('--hybrid', action='store_true', help='Add parallel BM25/fuzzy/suggestion combinations')
    p.add_argument('--auto', action='store_true', help='Add fuzzy AUTO, term suggestion AUTO, completion, and their combinations')
    p.add_argument('--es-ngram', action='store_true', help='Add Elasticsearch character ngram retrieval and parallel combinations')
    p.add_argument('--method-filter', help='Optional comma-separated exact method names to run')
    p.add_argument('--oom-rss-mib', type=int, default=0, help='Abort cleanly when process RSS exceeds this MiB (0 disables)')
    p.add_argument('--max-method-seconds', type=float, default=0, help='Stop a method after this wall time in seconds (0 disables)')
    p.add_argument('--corpus', help='JSONL {id, content}; whitespace-tokenized single-term benchmark')
    p.add_argument('--queries', help='JSONL {clean, typo, relevant_ids}; clean/typo must each be ONE term')
    p.add_argument('--output', default='results')
    p.add_argument('--timeout', type=float, default=10)
    a=p.parse_args()
    sizes=sorted(set(map(int,a.sizes.split(','))))
    edits=sorted(set(map(int,a.edits.split(','))))
    specs=a.grams.split(',')
    nsets={s: list(range(int(s.split('-')[0]),int(s.split('-')[-1])+1)) for s in specs}
    if min(sizes)<1 or not set(edits)<=set(range(4)) or min(a.samples,a.repeats,a.k,a.vocab,a.words,a.candidate_limit)<1 or a.timeout<=0 or (a.oom_rss_mib<0) or a.max_method_seconds<0 or any(min(ns)<1 for ns in nsets.values()):
        p.error('positive values required; edit distances supported: 0..3')
    if bool(a.corpus)!=bool(a.queries): p.error('--corpus and --queries must be supplied together')
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(42)
    if a.corpus:
        docs=[json.loads(l) for l in Path(a.corpus).read_text().splitlines() if l.strip()][:max(sizes)]
        for d in docs: d['id']=str(d['id'])
        tests=[json.loads(l) for l in Path(a.queries).read_text().splitlines() if l.strip()]
    else:
        alphabet='abcdefghijklmnopqrstuvwxyz'
        vocabulary=set()
        while len(vocabulary)<a.vocab:
            vocabulary.add(''.join(rng.choices(alphabet,k=8)))
        vocabulary=sorted(vocabulary)
        docs=[{'id':str(i),'content':' '.join([vocabulary[i%a.vocab]]+rng.choices(vocabulary,k=a.words-1))} for i in range(max(sizes))]
        tests=[]
        for clean in vocabulary[:min(a.samples,a.vocab)]:
            tests.append({'clean':clean,'typo':clean,'relevant_ids':[], 'bucket':'clean'})
            for d in [1,2,3]:
                chars=list(clean)
                for position in rng.sample(range(len(clean)),d):
                    chars[position]=rng.choice([x for x in alphabet if x!=chars[position]])
                tests.append({'clean':clean,'typo':''.join(chars),'relevant_ids':[], 'bucket':f'typo_{d}'})
    if len({d['id'] for d in docs})!=len(docs): raise ValueError('duplicate document IDs')
    for t in tests:
        if len(t['clean'].split())!=1 or len(t['typo'].split())!=1: raise ValueError('single-token clean/typo required')
        t.setdefault('bucket','clean' if t['clean']==t['typo'] else 'typo')
        t.setdefault('relevant_ids',[])
    session=requests.Session()
    if os.getenv('ES_API_KEY'): session.headers['Authorization']='ApiKey '+os.environ['ES_API_KEY']
    elif os.getenv('ES_USER'): session.auth=(os.environ['ES_USER'],os.getenv('ES_PASSWORD',''))
    def call(method,path,body=None,data=None):
        try:
            r=session.request(method,a.url.rstrip('/')+path,json=body,data=data,headers={'Content-Type':'application/x-ndjson'} if data else None,timeout=a.timeout)
        except requests.ConnectionError as e:
            raise RuntimeError(f"Cannot connect to Elasticsearch at {a.url}. Start Elasticsearch or pass its address with --url. ({e})") from e
        except requests.Timeout as e:
            raise RuntimeError(f"Elasticsearch request timed out at {a.url} (timeout={a.timeout}s). Increase --timeout or check the server. ({e})") from e
        if not r.ok:
            raise RuntimeError(f'Elasticsearch HTTP {r.status_code}: {r.text[:500]}')
        result=r.json()
        if result.get('timed_out') or result.get('_shards',{}).get('failed'): raise RuntimeError('ES timeout/shard failure')
        return result
    index='typo-grid-'+uuid.uuid4().hex[:12]
    es_version=None
    try:
        settings={'number_of_shards':1,'number_of_replicas':0,'refresh_interval':'-1'}
        mappings={'properties':{'content':{'type':'text','analyzer':'whitespace','similarity':'BM25'}}}
        if a.es_ngram:
            settings['analysis']={'tokenizer':{'typo_ngram_tokenizer':{'type':'ngram','min_gram':2,'max_gram':3}},'analyzer':{'typo_ngram':{'type':'custom','tokenizer':'typo_ngram_tokenizer'}},'normalizer':{'lowercase_keyword':{'type':'custom','filter':['lowercase']}}}
            mappings['properties']['ngram_content']={'type':'text','analyzer':'typo_ngram','search_analyzer':'whitespace'}
            mappings['properties']['ngram_term']={'type':'keyword','normalizer':'lowercase_keyword'}
            mappings['properties']['suggest']={'type':'completion','analyzer':'whitespace','preserve_separators':False,'max_input_length':50}
        call('PUT','/'+index,{'settings':settings,'mappings':mappings})
    except (RuntimeError,requests.HTTPError) as e:
        session.close()
        p.error(str(e))
    print('New index:',index,flush=True)
    def search(word,d=None):
        opts={'query':word}
        if d is not None: opts.update(fuzziness='AUTO' if d=='AUTO' else d,prefix_length=0,max_expansions=max(50,a.candidate_limit))
        r=call('POST','/'+index+'/_search?request_cache=false',{'size':a.k,'_source':False,'track_total_hits':False,'timeout':f'{int(a.timeout*1000)}ms','query':{'match':{'content':opts}}})
        return [h['_id'] for h in r['hits']['hits']],r['took']
    def ngram_search(word):
        r=call('POST','/'+index+'/_search?request_cache=false',{'size':a.k,'_source':False,'track_total_hits':False,'query':{'bool':{'should':[{'match':{'ngram_content':{'query':word,'operator':'or'}}},{'term':{'ngram_term':word.lower()}}],'minimum_should_match':1}}})
        return [h['_id'] for h in r['hits']['hits']],r['took']
    def suggest(word,mode,d):
        term={'field':'content','suggest_mode':mode,'sort':'score','size':a.candidate_limit,'max_edits':max(1,min(2,d)),'prefix_length':0,'min_word_length':1}
        r=call('POST','/'+index+'/_search?request_cache=false',{'size':0,'suggest':{'spell':{'text':word,'term':term}}})
        opts=r['suggest']['spell'][0]['options'] if r['suggest']['spell'] else []
        return (opts[0]['text'] if opts else word),r['took'],opts
    def completion_search(word):
        r=call('POST','/'+index+'/_search?request_cache=false',{'size':0,'suggest':{'completion':{'prefix':word,'completion':{'field':'suggest','size':a.candidate_limit,'skip_duplicates':True}}}})
        opts=r['suggest']['completion'][0]['options'] if r['suggest']['completion'] else []
        return (opts[0]['text'] if opts else word),r['took'],opts
    def parallel_hybrid_search(word,d,kind='fuzzy'):
        """Run requested retrievals concurrently, then fuse ranked IDs by RRF."""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures=[]
            if kind not in ('ngram','fuzzy_ngram'):
                futures.append(executor.submit(search,word,None))
            if kind in ('ngram','fuzzy_ngram'):
                futures.append(executor.submit(ngram_search,word))
            if kind in ('fuzzy','auto','fuzzy_ngram'):
                futures.append(executor.submit(search,word,'AUTO' if kind=='auto' else d))
            if kind=='completion':
                futures.append(executor.submit(_completion_retrieval,word))
            results=[future.result() for future in futures]
        scores=defaultdict(float)
        for hits,_ in results:
            for rank,doc_id in enumerate(hits,1): scores[doc_id]+=1/(60+rank)
        fused=sorted(scores,key=lambda doc_id:(-scores[doc_id],doc_id))[:a.k]
        return fused,sum(took for _,took in results)
    def _completion_retrieval(word):
        candidate,took,_=completion_search(word)
        hits,search_took=search(candidate)
        return hits,took+search_took
    fields=['docs','vocab','method','bucket','samples','errors','correction_accuracy','false_correction_rate','candidate_recall','recall_at_k','hit_at_k','mrr_at_k','p50_ms','p95_ms','max_ms','correction_p95_ms','es_took_p95_ms','build_seconds','python_peak_mib','index_bytes','index_seconds']
    samplefields=['docs','method','bucket','clean','input','corrected','candidate_hit','recall','hit','rr','latency_ms','correction_ms','es_took_ms','error']
    with (out/'summary.csv').open('w',newline='') as sf,(out/'samples.csv').open('w',newline='') as rf:
        sw=csv.DictWriter(sf,fieldnames=fields); sw.writeheader()
        rw=csv.DictWriter(rf,fieldnames=samplefields); rw.writeheader()
        count=0; cumulative_index=0
        try:
            for target in sizes:
                target=min(target,len(docs))
                if target<=count: continue
                tick=time.perf_counter()
                for start in range(count,target,500):
                    lines=[]
                    for doc in docs[start:min(start+500,target)]:
                        meta={'index':{'_id':doc['id']}}
                        source={'content':doc['content']}
                        if a.es_ngram:
                            source['ngram_content']=doc['content']
                            source['ngram_term']=list(set(doc['content'].split()))
                            source['suggest']=[{'input':word,'weight':1} for word in set(doc['content'].split())]
                        lines.extend([json.dumps(meta),json.dumps(source)])
                    r=call('POST','/'+index+'/_bulk',data='\n'.join(lines)+'\n')
                    if r.get('errors'): raise RuntimeError('bulk indexing failure')
                call('POST','/'+index+'/_refresh'); cumulative_index+=time.perf_counter()-tick; count=target
                df=Counter(); postings=defaultdict(set)
                for doc in docs[:target]:
                    for term in set(doc['content'].split()): df[term]+=1; postings[term].add(doc['id'])
                active_ids={d['id'] for d in docs[:target]}
                active=[]
                for test in tests:
                    relevant=({str(x) for x in test['relevant_ids']} & active_ids) if a.corpus else postings[test['clean']]
                    if relevant: active.append((test,relevant))
                if not active: print('No eligible qrels at',target); continue
                index_bytes=call('GET','/'+index+'/_stats/store')['indices'][index]['primaries']['store']['size_in_bytes']
                es_version=call('GET','/')['version']['number']
                methods=[('bm25_raw',None,None),('bm25_oracle',None,None)]
                for d in edits:
                    methods.append((f'symspell_d{d}','sym',d))
                    if d<=2:
                        methods.extend([(f'fuzzy_d{d}','fuzzy',d),(f'term_d{d}','term',d)])
                        if a.hybrid:
                            methods.extend([
                                (f'parallel_fuzzy_bm25_d{d}','parallel_fuzzy_bm25',d),
                                (f'term_bm25_d{d}','term_bm25',d),
                                (f'term_fuzzy_d{d}','term_fuzzy',d),
                                (f'term_parallel_fuzzy_bm25_d{d}','term_parallel_fuzzy_bm25',d),
                            ])
                        if a.auto:
                            methods.extend([(f'fuzzy_auto_d{d}','fuzzy_auto',d),(f'term_auto_d{d}','term_auto',d),(f'term_fuzzy_auto_d{d}','term_fuzzy_auto',d),(f'term_suggest_fuzzy_auto_d{d}','term_suggest_fuzzy_auto',d),(f'term_parallel_fuzzy_bm25_auto_d{d}','term_parallel_auto',d),(f'parallel_fuzzy_auto_bm25_d{d}','parallel_fuzzy_auto_bm25',d)])
                    if a.es_ngram:
                        methods.append((f'es_ngram_d{d}','es_ngram',d))
                        if a.hybrid: methods.append((f'parallel_es_ngram_bm25_d{d}','parallel_es_ngram_bm25',d))
                        if a.hybrid and d<=2: methods.append((f'parallel_fuzzy_es_ngram_d{d}','parallel_fuzzy_es_ngram',d))
                    if a.auto:
                        methods.append((f'completion_auto_d{d}','completion_auto',d))
                        if a.hybrid: methods.append((f'parallel_completion_bm25_d{d}','parallel_completion_bm25',d))
                    for spec in specs: methods.append((f'ngram_{spec}_d{d}',spec,d))
                if a.auto and 0 in edits:
                    methods.extend([('fuzzy_auto','fuzzy_auto',0),('term_auto','term_auto',1),('completion_auto','completion_auto',0)])
                methods.sort(key=lambda x:(x[1] in nsets and min(nsets[x[1]])==1, x[0]))
                if a.method_filter:
                    selected=set(a.method_filter.split(','))
                    methods=[m for m in methods if m[0] in selected]
                print(f'DOCS={target} VOCAB={len(df)} eligible={len(active)}',flush=True)
                stopped_methods=set()
                for name,kind,d in methods:
                    method_started=time.monotonic()
                    if a.oom_rss_mib:
                        import resource
                        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
                        if rss>a.oom_rss_mib:
                            print(f'OOM guard: RSS {rss:.0f} MiB exceeds --oom-rss-mib={a.oom_rss_mib}; stopping benchmark.',flush=True)
                            raise StopIteration
                    tracemalloc.start(); build=time.perf_counter(); obj=None
                    build_timed_out=False
                    if kind=='sym':
                        obj=SymSpell(max_dictionary_edit_distance=d,prefix_length=max(7,d+1))
                        for term,freq in df.items():
                            obj.create_dictionary_entry(term,freq)
                            if a.max_method_seconds and time.monotonic()-method_started>a.max_method_seconds:
                                build_timed_out=True; break
                    elif kind in nsets:
                        obj=defaultdict(set)
                        for term_i,term in enumerate(df):
                            for gram in grams(term,nsets[kind]): obj[gram].add(term)
                            if term_i%1000==0 and a.max_method_seconds and time.monotonic()-method_started>a.max_method_seconds:
                                build_timed_out=True; break
                    build=time.perf_counter()-build; peak=tracemalloc.get_traced_memory()[1]/2**20; tracemalloc.stop()
                    if build_timed_out:
                        print(f'Method time guard: {name} build exceeded {a.max_method_seconds}s; method skipped.',flush=True)
                        stopped_methods.add(name)
                        continue
                    def execute(test):
                        word=test['typo']; corrected=word; candidate_hit=None; took=0
                        start=time.perf_counter(); cstart=start
                        if kind=='sym':
                            candidates=obj.lookup(word,Verbosity.CLOSEST,max_edit_distance=d)
                            candidate_hit=any(c.term==test['clean'] for c in candidates)
                            if candidates: corrected=candidates[0].term
                        elif kind in nsets:
                            if word in df:
                                corrected=word; candidate_hit=(word==test['clean'])
                            else:
                                gs=grams(word,nsets[kind]); overlap=Counter()
                                for gram in gs: overlap.update(obj.get(gram,()))
                                # Retrieval by Dice overlap, then OSA edit-distance validation.
                                ranked=sorted(overlap,key=lambda t:(-2*overlap[t]/(len(gs)+len(grams(t,nsets[kind]))),-df[t],t))[:a.candidate_limit]
                                viable=[(OSA.distance(word,t,score_cutoff=d),-df[t],t) for t in ranked]
                                viable=sorted(x for x in viable if x[0]<=d)
                                candidate_hit=any(x[2]==test['clean'] for x in viable)
                                if viable: corrected=viable[0][2]
                        elif kind in ('term','term_bm25','term_fuzzy','term_parallel_fuzzy_bm25','term_auto','term_fuzzy_auto','term_parallel_auto','term_suggest_fuzzy_auto') and d>0:
                            mode='missing' if kind in ('term','term_bm25','term_fuzzy','term_parallel_fuzzy_bm25') else 'always'
                            corrected,st,options=suggest(word,mode,d); took+=st
                            candidate_hit=any(x['text']==test['clean'] for x in options) or word==test['clean']
                        elif kind in ('completion_auto','parallel_completion_bm25'):
                            corrected,st,options=completion_search(word); took+=st
                            candidate_hit=any(x['text']==test['clean'] for x in options) or word==test['clean']
                        elif kind=='term' or kind in ('term_bm25','term_fuzzy','term_parallel_fuzzy_bm25'):
                            candidate_hit=(word==test['clean'])
                        elif name=='bm25_oracle': corrected=test['clean']
                        correction_ms=(time.perf_counter()-cstart)*1000
                        if kind in ('parallel_fuzzy_bm25','parallel_fuzzy_auto_bm25','term_parallel_fuzzy_bm25','term_parallel_auto','parallel_es_ngram_bm25','parallel_completion_bm25','parallel_fuzzy_es_ngram'):
                            hybrid_word=corrected if kind in ('term_parallel_fuzzy_bm25','term_parallel_auto') else word
                            combo={'parallel_es_ngram_bm25':'ngram','parallel_completion_bm25':'completion','term_parallel_auto':'auto','parallel_fuzzy_auto_bm25':'auto','parallel_fuzzy_es_ngram':'fuzzy_ngram'}.get(kind,'fuzzy')
                            hits,server=parallel_hybrid_search(hybrid_word,d,combo)
                        elif kind=='term_bm25':
                            hits,server=search(corrected)
                        elif kind=='term_fuzzy':
                            hits,server=search(corrected,d)
                        elif kind=='term_parallel_fuzzy_bm25':
                            hits,server=search(corrected,d)
                        elif kind in ('term_fuzzy_auto','term_suggest_fuzzy_auto','fuzzy_auto'):
                            hits,server=search(corrected,'AUTO')
                        elif kind in ('term_auto','term_parallel_auto'):
                            hits,server=search(corrected)
                        elif kind in ('completion_auto','parallel_completion_bm25'):
                            hits,server=search(corrected)
                        elif kind in ('es_ngram','parallel_es_ngram_bm25'):
                            hits,server=ngram_search(word)
                        else:
                            hits,server=search(corrected,d if kind=='fuzzy' else None)
                        took+=server
                        return corrected,candidate_hit,hits,(time.perf_counter()-start)*1000,correction_ms,took
                    records=defaultdict(list)
                    oom_stop=False
                    request_error=False
                    method_timed_out=False
                    for rep in range(a.repeats):
                        order=list(active); random.Random(42+rep).shuffle(order)
                        for test,relevant in order:
                            if a.max_method_seconds and time.monotonic()-method_started > a.max_method_seconds:
                                print(f'Method time guard: {name} exceeded {a.max_method_seconds}s; stopping this method.',flush=True)
                                method_timed_out=True; break
                            if a.oom_rss_mib:
                                import resource
                                rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
                                if rss>a.oom_rss_mib:
                                    print(f'OOM guard: RSS {rss:.0f} MiB exceeds --oom-rss-mib={a.oom_rss_mib}; stopping benchmark.',flush=True)
                                    oom_stop=True; break
                            row={'docs':target,'method':name,'bucket':test['bucket'],'clean':test['clean'],'input':test['typo']}
                            try:
                                corrected,ch,hits,lat,clat,took=execute(test)
                                match=[i+1 for i,x in enumerate(hits) if x in relevant]
                                row.update(corrected=corrected,candidate_hit=ch,recall=len(set(hits)&relevant)/len(relevant),hit=int(bool(match)),rr=1/min(match) if match else 0,latency_ms=lat,correction_ms=clat,es_took_ms=took,error='')
                            except (requests.RequestException,RuntimeError) as e:
                                row['error']=str(e)[:150]
                                request_error=True
                            records[test['bucket']].append(row); rw.writerow(row); rf.flush()
                            failures=sum(bool(r.get('error')) for bucket_rows in records.values() for r in bucket_rows)
                            if request_error and failures>=max(3, math.ceil((len(order)*a.repeats)*0.5)):
                                print(f'Method error guard: {name} reached {failures} failures; skipping remaining samples.',flush=True)
                                method_timed_out=True
                                break
                        if oom_stop or method_timed_out: break
                    for bucket,rows in records.items():
                        good=[r for r in rows if not r['error']]; cs=[r for r in good if r['candidate_hit'] is not None]
                        mean=lambda key: statistics.mean(r[key] for r in good) if good else None
                        clean=[r for r in good if r['input']==r['clean']]
                        # Fuzzy does not output a corrected term, so correction metrics are N/A.
                        correction=statistics.mean(r['corrected']==r['clean'] for r in good) if good and kind!='fuzzy' else None
                        row=dict(docs=target,vocab=len(df),method=name,bucket=bucket,samples=len(rows),errors=len(rows)-len(good),correction_accuracy=correction,false_correction_rate=statistics.mean(r['corrected']!=r['clean'] for r in clean) if clean and kind!='fuzzy' else None,candidate_recall=statistics.mean(r['candidate_hit'] for r in cs) if cs else None,recall_at_k=mean('recall'),hit_at_k=mean('hit'),mrr_at_k=mean('rr'),p50_ms=pct([r['latency_ms'] for r in good],.5),p95_ms=pct([r['latency_ms'] for r in good],.95),max_ms=max([r['latency_ms'] for r in good],default=None),correction_p95_ms=pct([r['correction_ms'] for r in good],.95),es_took_p95_ms=pct([r['es_took_ms'] for r in good],.95),build_seconds=build,python_peak_mib=peak,index_bytes=index_bytes,index_seconds=cumulative_index)
                        sw.writerow(row); sf.flush()
                    print(name,'done',flush=True)
                    del obj
                    if method_timed_out:
                        stopped_methods.add(name)
                        continue
                    if oom_stop: raise StopIteration
                    if request_error:
                        errs=sum(len([r for r in rows if r['error']]) for rows in records.values())
                        total=sum(len(rows) for rows in records.values())
                        if total and errs/total >= 0.5:
                            raise RuntimeError(f'Stopping: {errs}/{total} requests failed for {name}; inspect ES/method compatibility.')
        except StopIteration:
            print('Benchmark stopped by OOM guard; completed results are retained.',flush=True)
        finally:
            session.close()
            run={'args':vars(a),'index':index,'seed':42,'elasticsearch_version':es_version if 'es_version' in locals() else None,'stopped_methods':sorted(stopped_methods) if 'stopped_methods' in locals() else [],'note':'Index retained. Latency errors excluded from percentiles; inspect errors. RSS and per-method time guards apply to index build and measurements.'}
            metadata=out/'dataset.json'
            if metadata.exists(): run['dataset']=json.loads(metadata.read_text(encoding='utf-8'))
            (out/'run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2))
            print('Results:',out,'Index retained:',index)

if __name__=='__main__': main()
