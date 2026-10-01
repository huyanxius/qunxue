#!/usr/bin/env python3
"""Offline merge/validate/deduplicate public exports; never copies raw snapshots."""
import argparse,copy,hashlib,json,re,unicodedata,os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from json_shards import load_json
from collections import Counter
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from datetime import datetime,timezone,date
ROOT=Path(__file__).resolve().parent

def h(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def norm(s):return ''.join(c.lower() for c in unicodedata.normalize('NFKC',s) if c.isalnum())
def canonical(u):
 p=urlsplit(u);return urlunsplit(('https',p.netloc.lower(),p.path.rstrip('/'),urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_')]),''))
def main():
 ap=argparse.ArgumentParser(description='Offline assembly of the fixed 2026-10-01 evidence snapshot. No network.')
 ap.add_argument('--output',type=Path,default=ROOT/'output',help='Output directory; relative paths are relative to caller cwd')
 ap.add_argument('--input-root',type=Path,default=ROOT/'data',help='Directory containing all four safe input shards')
 ap.add_argument('--preview',action='store_true')
 args=ap.parse_args(); output=args.output.resolve(); input_root=args.input_root.resolve()
 INPUTS=[('manual_curated',input_root/'manual-seed-records.json'),('algorithm_harvested',input_root/'journals/records.json'),('algorithm_harvested',input_root/'society/records.json'),('algorithm_harvested',input_root/'practice/practice-records.json')]
 absent=[str(p) for _,p in INPUTS if not p.is_file()]
 if absent:ap.error('Missing required input shard(s): '+', '.join(absent))
 if output==input_root or output in [p.parent for _,p in INPUTS]:ap.error('Output must not overwrite input shards')
 output.mkdir(parents=True,exist_ok=True)
 out=[];rejected=[];duplicates=[];by_url={};by_title={};input_counts={};allowed_hosts=set();body_hashes={}
 for method,path in INPUTS:
  raw=load_json(path);raw=raw.get('records',[]) if isinstance(raw,dict) else raw
  input_counts[str(path.relative_to(input_root))]=len(raw)
  for original in raw:
   r=copy.deepcopy(original);r['collection_method']=method;r['human_full_text_reviewed']=False
   r.setdefault('external_id',('curated:' if method=='manual_curated' else 'harvested:')+r['id'])
   r.setdefault('source_publisher',r.get('hosting_authority'))
   if isinstance(r.get('authors'),list):r['authors']=[str(a).strip() for a in r['authors'] if str(a).strip()]
   r.setdefault('source_published_at',None)
   r.setdefault('published_at_precision','day' if r.get('published_at') else 'issue')
   r.setdefault('published_at_display',r.get('published_at') or f"{r.get('publication_year','年份未知')}年第{r.get('publication_issue','未知')}期")
   r.setdefault('missing_reasons',{})
   r.setdefault('topics',[])
   r.setdefault('verification_status','lead_only')
   r.setdefault('material_type','research_abstract')
   r['stream']='practice' if r['material_type']=='official_practice' else 'research'
   if not r.get('summary'):
    r['summary']=('主题词命中：'+'、'.join(r['topics'][:5])+'。' if r['topics'] else '原刊社会学研究摘要线索。')+'这是确定性主题提要，未人工提炼研究发现。'
    r['summary_method']='deterministic_topic_label_template; no inference about findings'
    r['missing_reasons'].pop('summary',None)
   if r.get('short_excerpt') and r.get('evidence'):
    for e in r['evidence']:
     if e.get('excerpt_pointer')=='short_excerpt':e['snippet']=r.pop('short_excerpt');e.pop('excerpt_pointer',None);break
   for e in r.get('evidence',[]):
    e.setdefault('url',r['url']);e.setdefault('snippet',None);e.setdefault('supports',['source_readability'])
   for k in ('authors','research_question','methods','data','sample','findings','limitations'):
    r.setdefault(k,None)
    if r[k] is None:r['missing_reasons'].setdefault(k,'公开来源未披露，或本轮未作人工结构化核验；不推断补齐。')
   if method=='manual_curated':
    minimal={k:r.get(k) for k in ('title','authors','url','published_at','source_name','evidence')}
    r['source_snapshot']['minimal_evidence_sha256']=h(minimal)
    r['source_snapshot']['hash_scope']='curated_metadata_and_excerpt_not_original_http_response'
    r['readable_material_verified']=True
    r['readability_basis']='previous_manual_opened_official_source; see seed SOURCE_AUDIT.md'
   else:
    r['readable_material_char_count']=r.get('abstract_char_count') or r.get('body_char_count') or r.get('source_snapshot',{}).get('abstract_char_count')
    r['readable_material_verified']=bool(r['readable_material_char_count'] and r['readable_material_char_count']>=60)
    r['readability_basis']=r.get('abstract_read_status') or r.get('evidence_scope')
   if not all(r.get(k) for k in ('title','url','source_name','evidence','verification_note')) or not r['readable_material_verified']:
    rejected.append({'id':r.get('id'),'reason':'missing_minimum_metadata_or_readable_abstract_body'});continue
   pub=r.get('published_at')
   if pub:
    try:date.fromisoformat(pub)
    except ValueError:rejected.append({'id':r['id'],'reason':'invalid_date','value':pub});continue
    if pub>'2026-10-01':rejected.append({'id':r['id'],'reason':'future_date'});continue
   r['temporal_eligible']=bool(pub and r['published_at_precision']=='day')
   r['within_preferred_window']=bool(pub and '2025-10-01'<=pub<='2026-10-01') if pub else None
   r['sampling_inference_limit']='仅描述已采可读文章样本；不能把采集量、配额或词频当作学科总体增长、发生率或因果证据。'
   url=canonical(r['url']);title=norm(r['title']);duplicate_index=by_url.get(url,by_title.get(title))
   if duplicate_index is not None:
    keep=out[duplicate_index]
    keep.setdefault('alternate_sources',[]).append({'url':r['url'],'source_publisher':r.get('source_publisher'),'collection_method':method,'external_id':r['external_id']})
    duplicates.append({'kept_id':keep['id'],'removed_id':r['id'],'reason':'same_canonical_url' if url in by_url else 'same_normalized_title','removed_url':r['url']});continue
   content_hash=r.get('abstract_sha256') or r.get('body_sha256') or r.get('source_snapshot',{}).get('abstract_sha256')
   if content_hash and content_hash in body_hashes:
    rejected.append({'id':r['id'],'reason':'duplicate_readable_text_hash_across_different_title','other_id':body_hashes[content_hash]});continue
   if content_hash:body_hashes[content_hash]=r['id']
   by_url[url]=len(out);by_title[title]=len(out);out.append(r);allowed_hosts.add(urlsplit(url).hostname)
 required=['id','external_id','title','authors','source_name','source_publisher','url','published_at','published_at_precision','published_at_display','source_published_at','summary','topics','evidence','verification_note','verification_status','material_type','source_snapshot']
 errors=[]
 for r in out:
  for k in required:
   if k not in r:errors.append({'id':r['id'],'missing_key':k})
  if r['collection_method']=='algorithm_harvested':
   quotes=[e.get('snippet') for e in r['evidence'] if e.get('snippet')]
   if sum(len(s) for s in quotes)>25:errors.append({'id':r['id'],'quote_chars':sum(len(s) for s in quotes)})
   for k in ['full_text','body','abstract','article_text','raw_html']:
    if r.get(k):errors.append({'id':r['id'],'full_content_field':k})
 assert not errors,errors
 assert len({r['id'] for r in out})==len(out)
 count=lambda key:dict(sorted(Counter(str(r.get(key)) for r in out).items()))
 dates=[r for r in out if r['temporal_eligible']]
 stats={'record_count':len(out),'input_counts':input_counts,'duplicates_removed':len(duplicates),'rejected_records':len(rejected),'source_counts':count('source_name'),'stream_counts':count('stream'),'verification_status_counts':count('verification_status'),'collection_method_counts':count('collection_method'),'publication_year_counts':dict(sorted(Counter(str(r.get('publication_year') or (r.get('published_at') or '')[:4] or 'unknown') for r in out).items())),'date_precision_counts':count('published_at_precision'),'dated_in_preferred_window':sum(r.get('within_preferred_window') is True for r in out),'dated_outside_preferred_window':sum(r.get('within_preferred_window') is False for r in out),'unknown_exact_date_excluded_from_months':sum(not r['temporal_eligible'] for r in out),'monthly_counts_for_audit_not_growth':{stream:dict(sorted(Counter(r['published_at'][:7] for r in dates if r['stream']==stream).items())) for stream in ['research','practice']},'unique_canonical_urls':len(by_url),'unique_normalized_titles':len(by_title),'schema_errors':errors}
 manifest=[{'host':host,'source_names':sorted({r['source_name'] for r in out if urlsplit(r['url']).hostname==host}),'record_count':sum(urlsplit(r['url']).hostname==host for r in out)} for host in sorted(allowed_hosts)]
 package={'schema_version':'2.0','generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'snapshot_as_of':'2026-10-01','reproduction_mode':'fixed_2026_10_01_snapshot_offline_assembly','collection_complete':not args.preview,'coverage_complete':False,'preferred_publication_window':{'from':'2025-10-01','through':'2026-10-01'},'record_count':len(out),'sampling_strategy':{'manual_seed':'12 individually researched items; retained with manual curation label','society':'recent official annual contents; one record per readable Chinese abstract; capped at 24 successful records','social_construction':'latest available issue pages in 2024–2026, capped near100 valid abstracts; not the full field','practice':'deterministic monthly quota up to5 entries per month in 2025-10..2026-09 selected via topical titles; not probability sampling','allowed_inference':'sample-internal topic distribution, source/date composition, retrieval; no publication-growth or real-world incidence claim'},'source_manifest':manifest,'statistics':stats,'records':out}
 prefix='frontier-corpus-preview' if args.preview else 'frontier-corpus'
 (output/f'{prefix}.json').write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
 if not args.preview:
  (output/'frontier-corpus-records.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
  (output/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
  (output/'validation-report.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
  (output/'deduplication-report.json').write_text(json.dumps({'algorithm':'canonical URL and NFKC alphanumeric normalized title, curated records first, then readable-content hash check','duplicates':duplicates,'rejected':rejected,'final_unique':len(out)},ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
