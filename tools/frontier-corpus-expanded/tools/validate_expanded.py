#!/usr/bin/env python3
"""Offline delivery integrity; intentionally performs no HTTP requests."""
import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--output',type=Path,default=ROOT/'build',help='Directory produced by assemble_expanded.py.')
 args=ap.parse_args();output=args.output
 snapshot=json.loads((ROOT/'snapshot.json').read_text(encoding='utf-8'))
 for name,expected in snapshot['expected_output_sha256'].items():
  actual=hashlib.sha256((output/name).read_bytes()).hexdigest()
  assert actual==expected,(name,actual,expected)
 d=json.loads((output/'frontier-corpus.json').read_text(encoding='utf-8'));rows=d['records'];index=json.loads((output/'research-index.json').read_text(encoding='utf-8'));briefs=json.loads((output/'topic-briefs.json').read_text(encoding='utf-8'))['briefs'];byid={r['id']:r for r in rows}
 assert len(rows)==len(byid)==276
 assert len({r['url'] for r in rows})==276
 assert all(r['summary_method']==r['extraction_method']=='assistant_evidence_synthesis' for r in rows)
 assert all(len(r['summary'])>=25 and r.get('why_read') and r.get('research_question') and isinstance(r['findings'],list) and r['findings'] for r in rows)
 assert all(r.get('analysis_evidence') for r in rows)
 assert all(r['analysis_scope'] in ['abstract','practice_body'] for r in rows)
 assert all(r['verification_status']=='lead_only' for r in rows if r['stream']=='research')
 assert all(r['human_full_text_reviewed'] is False for r in rows)
 assert len({r['summary'] for r in rows})==276
 for r in rows:
  for field in ['raw_html','full_text','abstract','body','article_text']:assert not r.get(field),(r['id'],field)
  if r['collection_method']=='algorithm_harvested':assert sum(len(x.get('snippet') or '') for x in r['evidence'])<=25,r['id']
  for evidence in r['analysis_evidence']:assert all(0<=i<len(r['evidence']) for i in evidence['evidence_indexes'])
  if r.get('published_at'):assert r['published_at']<='2026-10-01'
 for brief in briefs:
  assert len(set(brief['evidence_record_ids']))>=2
  assert all(x in byid for x in brief['evidence_record_ids'])
  content=brief['research_brief']
  for key in ['consensus','differences','methods']:
   for claim in content[key]:
    assert set(claim['evidence_record_ids'])<=set(brief['evidence_record_ids'])
    if key in ['consensus','differences']:assert len(set(claim['evidence_record_ids']))>=2
  for key in ['development','research_implication']:assert set(content[key]['evidence_record_ids'])<=set(brief['evidence_record_ids'])
  for read in content['priority_reads']:assert read['record_id'] in brief['evidence_record_ids']
 quarantined=['research-shjs-2023-554','research-shjs-2023-555','research-shjs-2025-665','research-shjs-2025-671']
 assert not set(quarantined)&set(byid)
 assert not set(quarantined)&{r['id'] for r in index['records']}
 assert index['record_count']==517 and index['bulk_journal_readable_record_count']==508
 assert len(index['records'])==len({r['id'] for r in index['records']})==517
 counts=Counter(r.get('issue_id') for r in rows)
 for issue in d['issue_coverage']:
  assert issue['included_count']==counts[issue['issue_id']]
  if issue['coverage_complete']:assert issue['candidate_count']==issue['readable_count']==issue['included_count']==issue['analyzed_count']
 media=[m for r in rows for m in r.get('media',[])];assert len(media)==2
 assert all(m['url'].startswith('https://www.society.shu.edu.cn/article/') for m in media)
 report={'passed':True,'display_records':len(rows),'reviewed_research':273,'reviewed_practice':3,'bulk_readable_journal_index':508,'research_index_with_reviewed_supplements':517,'awaiting_assistant_synthesis':244,'briefs':len(briefs),'evidence_matrix_rows':len(json.loads((output/'evidence-matrix.json').read_text(encoding='utf-8'))['rows']),'verified_media':len(media),'complete_display_issues':sum(x['coverage_complete'] for x in d['issue_coverage']),'quarantined_ids_absent':quarantined,'unique_summaries':276,'raw_full_content_exported':False,'validation_scope':'Offline artifact integrity only; no source collection or remote publication'}
 (output/'final-integrity-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
