#!/usr/bin/env python3
"""Rebuild the frozen 2026-10-01 reviewed corpus offline, byte for byte."""
import argparse,copy,hashlib,json,re,unicodedata
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from json_shards import load_json
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]

def load(path,default=None):
    return load_json(path) if path.exists() else default

def rows(path):
    obj=load(path,[])
    return obj.get('records',[]) if isinstance(obj,dict) else obj

def norm(title):return ''.join(x.lower() for x in unicodedata.normalize('NFKC',title) if x.isalnum())
def digest(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(path,obj):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'build',help='Output directory; relative paths resolve from the caller cwd.')
    ap.add_argument('--complete',action='store_true',help='Compatibility flag; this frozen snapshot is already complete.')
    args=ap.parse_args()
    snapshot=load(ROOT/'snapshot.json')
    if not snapshot:
        ap.error('Missing snapshot.json; use the complete frozen tool directory.')
    for name,expected in snapshot['input_sha256'].items():
        path=ROOT/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            ap.error(f'Missing or changed frozen input: {name}')
    if args.output.resolve()==ROOT:
        ap.error('Choose a separate output directory (default: build).')
    args.output.mkdir(parents=True,exist_ok=True)
    inputs=[ROOT/'progress/initial-enriched-records.json',ROOT/'ruc/reviewed-records.json',ROOT/'society/enriched-records.json']
    prior_dates=load(ROOT/'progress/prior-verified-publication-dates.json',{})
    media_overrides=load(ROOT/'media-overrides.json',{})
    collected={};by_title={};aliases={};errors=[]
    for path in inputs:
        for original in rows(path):
            r=copy.deepcopy(original);identifier=r['id'];key=norm(r['title'])
            prior=prior_dates.get(identifier)
            if prior and not r.get('published_at'):
                for k in ['published_at','published_at_precision','published_at_display','source_published_at','date_basis']:r[k]=prior.get(k)
                r['publication_date_evidence']={'source_url':prior['url'],'source_snapshot':prior['source_snapshot'],'basis':'previously_verified_explicit_publication_date_retained'}
            if key in by_title and by_title[key]!=identifier:
                aliases[identifier]=by_title[key];identifier=by_title[key];r['id']=identifier
            by_title[key]=identifier
            if identifier in collected:
                previous=collected[identifier]
                # Carry exact publication dates already actually verified on article pages.
                if previous.get('published_at') and not r.get('published_at'):
                    for k in ['published_at','published_at_precision','published_at_display','source_published_at','date_basis']:
                        if k in previous:r[k]=previous[k]
                    r['publication_date_evidence']=previous.get('publication_date_evidence') or previous.get('source_snapshot')
                r['topics']=list(dict.fromkeys(previous.get('topics',[])+r.get('topics',[])))
            r.setdefault('collection_method','algorithm_harvested')
            r['stream']='practice' if r.get('material_type')=='official_practice' else 'research'
            for k in ['source_published_at','research_question','methods','data','sample','limitations','why_read']:r.setdefault(k,None)
            if isinstance(r.get('findings'),str):r['findings']=[r['findings']]
            r['source_id']={'社会建设':'social-construction','社会':'society'}.get(r['source_name'],r.get('source_id'))
            if r['source_id'] and r.get('publication_year') and r.get('publication_issue'):r['issue_id']=f"{r['source_id']}:{r['publication_year']}:{r['publication_issue']}"
            r['temporal_eligible']=r.get('published_at_precision')=='day' and bool(r.get('published_at'))
            r['within_preferred_window']=('2025-10-01'<=r['published_at']<='2026-10-01') if r['temporal_eligible'] else None
            if not r.get('analysis_evidence'):
                r['analysis_evidence']=[{'field':f,'statement':statement,'evidence_indexes':[0]} for f in ['summary','research_question','methods','findings','why_read'] for statement in (r[f] if isinstance(r.get(f),list) else [r.get(f)]) if statement]
            fields_ok=all(r.get(k) for k in ['summary','research_question','findings','why_read','evidence','analysis_evidence'])
            marked=r.get('summary_method')=='assistant_evidence_synthesis' and r.get('extraction_method')=='assistant_evidence_synthesis'
            if not fields_ok or not marked:errors.append({'id':identifier,'reason':'not_display_ready_assistant_synthesis'});continue
            if any(not isinstance(s,str) for s in r['findings']):errors.append({'id':identifier,'reason':'findings_must_be_strings'});continue
            for claim in r['analysis_evidence']:
                assert claim.get('evidence_indexes') and all(isinstance(i,int) and 0<=i<len(r['evidence']) for i in claim['evidence_indexes']),identifier
            for forbidden in ['raw_html','full_text','abstract','body','article_text']:
                assert not r.get(forbidden),(identifier,forbidden)
            r['media']=media_overrides.get(identifier,r.get('media',[]))
            r['display_ready']=True;r['human_full_text_reviewed']=False
            collected[identifier]=r
    records=list(collected.values());counts=Counter(r.get('issue_id') for r in records)
    coverage=[]
    for source,path in [('social-construction',ROOT/'ruc/collection/issue-coverage.json'),('society',ROOT/'society/coverage-final.json')]:
        for x in load(path,[]):
            year=x.get('publication_year',x.get('year'));issue=x.get('publication_issue',x.get('issue'));iid=f'{source}:{year}:{issue}'
            candidates=x.get('candidate_count',x.get('research_candidates',0));readable=x.get('readable_count',x.get('parsed_readable_records',0));retained=x.get('retained_count',x.get('included_records',readable))
            proved=(x.get('directory_processing_complete') and x.get('all_research_candidates_have_retained_abstract')) if source=='social-construction' else x.get('coverage_complete',False)
            included=counts[iid]
            coverage.append({'source_name':x['source_name'],'source_id':source,'issue_id':iid,'publication_year':year,'publication_issue':issue,'publication_month':x.get('publication_month') or ((x.get('published_at') or '')[:7] or None),'candidate_count':candidates,'readable_count':readable,'retained_source_count':retained,'included_count':included,'analyzed_count':included,'coverage_complete':bool(proved and candidates==readable==included and candidates>0),'issue_url':x.get('issue_url',x.get('url')),'excluded_nonresearch_count':x.get('excluded_nonresearch_count',x.get('excluded_count',0)),'missing_abstract_count':x.get('missing_abstract_count',0),'collision_quarantined_count':x.get('collision_quarantined_count',0),'source_coverage_complete':bool(proved),'coverage_note':x.get('coverage_note') or 'Display denominator includes only records with completed source-grounded assistant synthesis; research candidates must all be readable and included for comparable shares.'})
    pool=[]
    for path in [ROOT/'ruc/collection/records.json',ROOT/'society/collection/records.json',ROOT/'society-pagination/page2-candidates.json']:
        pool.extend(rows(path))
    metadata_count=len({norm(r['title']):r for r in pool})
    pool_unique={norm(r['title']):r for r in pool if (r.get('readable_abstract') is True or r.get('abstract_char_count',0)>=60 or r.get('source_snapshot',{}).get('abstract_char_count',0)>=60) and not r.get('explicit_nonresearch',False)}
    stats={'display_record_count':len(records),'research_count':sum(r['stream']=='research' for r in records),'practice_count':sum(r['stream']=='practice' for r in records),'all_display_records_have_assistant_synthesis':not errors,'source_read_research_pool_count':len(pool_unique),'source_metadata_index_count':metadata_count,'records_with_verified_media':sum(bool(r.get('media')) for r in records),'verified_media_count':sum(len(r.get('media',[])) for r in records),'source_counts':dict(Counter(r['source_name'] for r in records)),'issue_precision_count':sum(r.get('published_at_precision')=='issue' for r in records),'exact_day_count':sum(r['temporal_eligible'] for r in records),'source_issue_count':len(coverage),'display_complete_issue_count':sum(x['coverage_complete'] for x in coverage),'cohort_complete_issues':{str(y):{s:sum(x['coverage_complete'] and x['publication_year']==y and x['source_id']==s and x['publication_issue'] in [1,2,3] for x in coverage) for s in ['society','social-construction']} for y in [2023,2024,2025,2026]},'rejected_not_display_ready':errors,'records_sha256':digest(records)}
    all_research_index=dict(pool_unique)
    for r in records:
        if r['stream']=='research':all_research_index[norm(r['title'])]=r
    stats['bulk_journal_readable_research_index_count']=len(pool_unique)
    stats['research_index_count_with_reviewed_supplements']=len(all_research_index)
    stats['indexed_research_awaiting_synthesis']=len(all_research_index)-stats['research_count']
    write(args.output/'research-index.json',{'record_count':len(all_research_index),'bulk_journal_readable_record_count':len(pool_unique),'display_ready_research_count':stats['research_count'],'awaiting_synthesis_count':stats['indexed_research_awaiting_synthesis'],'not_all_indexed_records_are_display_ready':True,'records':list(all_research_index.values())})
    package={'schema_version':'3.0','generated_at':snapshot['generated_at'],'collection_complete':snapshot['collection_complete'],'coverage_complete':False,'record_count':len(records),'preferred_publication_window':snapshot['preferred_publication_window'],'sampling_strategy':{'design':'Observed complete journal issue cohorts, prioritizing matched issues 1–3 in 2023–2026; historical 2021–2022 used where accessible. Only completed assistant source-abstract paraphrases enter display records.','comparison':'Within-source same-issue cohort topic shares only after complete denominator and enrichment verification. Unknown exact dates are excluded from calendar-month charts.','population_limit':'Selected journal corpus, not all sociology research or social-world prevalence.'},'statistics':stats,'issue_coverage':coverage,'records':records}
    for filename,obj in [('frontier-corpus.json',package),('frontier-corpus-records.json',records),('issue-coverage.json',coverage),('validation-report.json',stats),('id-aliases.json',aliases)]:write(args.output/filename,obj)
    # Reviewed briefs are independent frozen artifacts, not re-generated claims.
    for filename in ['topic-briefs.json','evidence-matrix.json']:
        (args.output/filename).write_bytes((ROOT/filename).read_bytes())
    for filename,expected in snapshot['expected_output_sha256'].items():
        actual=hashlib.sha256((args.output/filename).read_bytes()).hexdigest()
        if actual!=expected:
            raise ValueError(f'Frozen output mismatch: {filename}: {actual}')
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
