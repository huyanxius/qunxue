#!/usr/bin/env python3
"""Public, single-host, rate-limited collection. No auth, no challenge bypass.
Raw article bodies with noarchive are processed in memory and never persisted.
Export contains metadata, <=24-character evidence, hashes and official keywords.
"""
from runtime import add_run_arguments,prepare_run,open_public,AccessChallenge,assert_no_access_challenge
import argparse, hashlib, json, re, time, urllib.request, urllib.error, urllib.parse, urllib.robotparser, fcntl
from datetime import datetime, timezone
from pathlib import Path
from lxml import html
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from json_shards import load_json
BASE='https://www.society.shu.edu.cn'
UA='QunxueResearchCollector/1.0 (public academic metadata; noncommercial; rate limited)'
OUT=None
LOG=None
last=0.0; rp=urllib.robotparser.RobotFileParser(); robots_ready=False;stopped=False

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def sha(b): return hashlib.sha256(b).hexdigest()
def log(x):
 with LOG.open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
def get(u,kind='article'):
 global last,stopped
 if stopped:raise RuntimeError('Host stopped after access/rate restriction')
 if urllib.parse.urlsplit(u).hostname!='www.society.shu.edu.cn':raise ValueError('Outside allowed host')
 if robots_ready and not rp.can_fetch(UA,u):
  log({'at':now(),'url':u,'kind':kind,'outcome':'robots_disallowed'});return None
 for attempt in range(2):
  time.sleep(max(0,max(3.0,rp.crawl_delay(UA) or rp.crawl_delay('*') or 0)-(time.monotonic()-last)))
  started=now();last=time.monotonic()
  try:
   req=urllib.request.Request(u,headers={'User-Agent':UA,'Accept':'text/html,text/plain;q=0.9'})
   with open_public(req,timeout=40) as r:
    b=r.read(6_000_000);h=dict(r.headers);final=r.geturl();status=r.status
   assert_no_access_challenge(b)
   if urllib.parse.urlsplit(final).hostname!='www.society.shu.edu.cn':raise ValueError('Unexpected cross-host redirect')
   rec={'at':started,'url':u,'final_url':final,'kind':kind,'status':status,'bytes':len(b),'sha256':sha(b),'attempt':attempt+1,'x_robots_tag':h.get('X-Robots-Tag')}
   log(rec);return b,rec
  except AccessChallenge as e:
   stopped=True;log({'at':started,'url':u,'kind':kind,'outcome':'access_challenge_stop','error':str(e)})
   raise
  except urllib.error.HTTPError as e:
   log({'at':started,'url':u,'kind':kind,'status':e.code,'attempt':attempt+1,'outcome':'http_error'})
   if e.code in (401,403,429):stopped=True;raise RuntimeError(f'Stopping host on HTTP {e.code}')
   if e.code in (404,410):return None
   if attempt==0:time.sleep(12)
  except (urllib.error.URLError,TimeoutError,ValueError) as e:
   log({'at':started,'url':u,'kind':kind,'error':str(e),'attempt':attempt+1})
   if attempt==0:time.sleep(12)
 return None

def doc(b):return html.fromstring(b.decode('utf-8','replace'))
def clean(s):return re.sub(r'\s+',' ',s).strip()
def metas(d,key):return [clean(v) for v in d.xpath('//meta[translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")=$key]/@content',key=key.lower()) if clean(v)]
def meta(d,key):
 a=metas(d,key);return a[0] if a else None

def parse_article(b,req):
 d=doc(b); directives=','.join(metas(d,'robots')+[str(req.get('x_robots_tag') or '')]).lower()
 if any(x in directives.split(',') for x in ('noindex','none')):return None,'robots_meta_noindex'
 title=meta(d,'citation_title') or meta(d,'DC.Title')
 if not title or not re.search(r'[\u4e00-\u9fff]',title):return None,'missing_chinese_title'
 blocks=d.xpath('//*[@id="C3"]')
 if not blocks:
  blocks=d.xpath('//*[@id="collapseOne"]/div/p[strong[contains(text(),"摘要")]][1]')
 abstract=re.sub(r'^摘要\s*[:：]\s*','',clean(' '.join(e.text_content() for e in blocks)))
 if len(abstract)<60:
  panels=d.xpath('//*[@id="collapseOne"]/div')
  content=clean(' '.join(e.text_content() for e in panels))
  am=re.search(r'摘要\s*[:：]\s*(.*?)(?:关键词\s*[:：]|Abstract\s*[:：])',content,re.S)
  if am:abstract=am.group(1).strip()
 if len(abstract)<60 or not re.search(r'[\u4e00-\u9fff]',abstract):return None,'no_readable_abstract'
 panel=clean(' '.join(d.xpath('//*[@id="divPanel"]//text()')))
 pub=re.search(r'出版日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})',panel)
 online=re.search(r'发布日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})',panel)
 pub=pub.group(1) if pub else None;online=online.group(1) if online else None
 if pub and pub>'2026-10-01':return None,'future_publication'
 url=meta(d,'citation_abstract_html_url') or req['final_url']
 aid=re.search(r'abstract(\d+)',url)
 ext='society:'+(aid.group(1) if aid else sha(url.encode())[:16])
 authors=meta(d,'citation_authors') or meta(d,'DC.Contributor')
 authors=[a for a in re.split(r'[,，;；、|]+',authors or '') if a.strip()] or None
 keywords=meta(d,'keywords') or meta(d,'DC.Keywords') or ''
 topics=[x.strip() for x in re.split(r'[,，;；]+',keywords) if x.strip()][:10]
 volume=meta(d,'citation_volume');issue=meta(d,'citation_issue')
 year=int(pub[:4]) if pub else (int(re.search(r'/Y(\d{4})/',req['url']).group(1)) if re.search(r'/Y(\d{4})/',req['url']) else None)
 snippet=abstract[:24]
 snapshot={'kind':'minimal_evidence_noarchive' if 'noarchive' in directives else 'minimal_evidence','captured_at':req['at'],'http_status':200,'response_sha256':req['sha256'],'response_bytes':req['bytes'],'abstract_sha256':sha(abstract.encode()),'abstract_char_count':len(abstract),'page_robots':directives,'raw_html_persisted':False,'local_evidence_file':f'society/evidence/{ext.replace(":","-")}.json','date_locator':'#divPanel 中文出版日期/发布日期；不采用meta citation_date冒充出版日'}
 missing={k:'算法仅抽取书目、日期、关键词与摘要线索，未人工核验全文中的该字段。' for k in ['research_question','methods','data','sample','findings','limitations']}
 if not pub:missing['published_at']='原页未找到明确的中文出版日期；未用网页发布日期替代。'
 if not authors:missing['authors']='未解析到中文作者元数据。'
 if not topics:missing['topics']='原页未提供可解析关键词。'
 r={'id':'algorithm-'+ext.replace(':','-'),'external_id':ext,'title':title,'authors':authors,'published_at':pub,'published_at_precision':'day' if pub else 'issue','published_at_display':pub or f'{year or "年份未知"}年第{issue or "未知"}期','publication_year':year,'publication_volume':volume,'publication_issue':int(issue) if issue and issue.isdigit() else issue,'publication_pages':'–'.join(x for x in [meta(d,'citation_firstpage'),meta(d,'citation_lastpage')] if x) or None,'doi':meta(d,'citation_doi'),'source_name':'社会','source_publisher':'上海大学《社会》编辑部','source_published_at':online,'source_date_label':'原站发布日期（与出版日期分开）','url':url,'material_type':'research_abstract','source_scope':'journal_original_abstract','summary':('议题涉及'+ '、'.join(topics[:4])+'。' if topics else '社会学论文公开摘要线索。')+'已读取原刊中文摘要，具体研究结论尚未人工复核。','summary_method':'deterministic_official_keyword_template; evidence is a 24-character excerpt','topics':topics,'research_question':None,'methods':None,'data':None,'sample':None,'findings':None,'limitations':None,'missing_reasons':missing,'verification_status':'lead_only','verification_note':'算法实际读取原期刊网页中文摘要并校验元数据和日期，未人工复核论文全文。','evidence_scope':'original_journal_abstract_only','discovered_at':req['at'],'collection_method':'algorithm_harvested','evidence':[{'snippet':snippet,'locator':'原刊网页 #collapseOne 中文摘要首段（#C3或strong摘要同段）开头；标题/作者见citation元数据','url':url,'supports':['readable_abstract','metadata']}],'source_snapshot':snapshot,'source_relationships':[{'relation':'discovered_via_official_annual_contents','url':req['discovery_url']}],'editorial_caveat':'本批采集覆盖可访问期刊页面，不代表社会学全部发表量；关键词频率仅用于本语料内描述。','within_preferred_window':bool(pub and '2025-10-01'<=pub<='2026-10-01'),'temporal_eligible':bool(pub),'date_basis':'explicit_chinese_publication_label' if pub else 'issue_only'}
 evidence={'url':url,'title':title,'authors':authors,'published_at':pub,'source_published_at':online,'snippet':snippet,'locator':r['evidence'][0]['locator'],'snapshot':snapshot}
 (OUT/'evidence'/f'{ext.replace(":","-")}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
 return r,None

def main():
 global robots_ready,OUT,LOG
 ap=argparse.ArgumentParser(description='Fixed 2026-10-01 sample recipe; live pages can change')
 add_run_arguments(ap);ap.add_argument('--limit',type=int,default=24);ap.add_argument('--years',default='2026,2025');args=ap.parse_args()
 OUT=prepare_run(ap,args,['www.society.shu.edu.cn']);LOG=OUT/'requests.jsonl'
 (OUT/'evidence').mkdir(exist_ok=True)
 result=get(BASE+'/robots.txt','robots')
 if not result:raise RuntimeError('robots unavailable; refuse crawl')
 rb,rr=result;rp.parse(rb.decode('utf-8','replace').splitlines());robots_ready=True
 (OUT/'robots.json').write_text(json.dumps({'url':BASE+'/robots.txt','fetched_at':rr['at'],'sha256':rr['sha256'],'text':rb.decode('utf-8','replace')},ensure_ascii=False,indent=2), encoding='utf-8')
 items={}
 for ys in args.years.split(','):
  year=int(ys); u=f'{BASE}/CN/article/showVolumnArticle.do?nian={year}&juan={year-1980}'
  res=get(u,'annual_contents')
  if not res:continue
  b,req=res;d=doc(b)
  for a in d.xpath('//a[@href]'):
   h=urllib.parse.urljoin(u,a.attrib['href']).split('#')[0]
   if re.search(r'/CN/Y'+ys+r'/V\d+/I\d+/\d+$',h) and len(clean(a.text_content()))>4:items.setdefault(h,{'url':h,'discovery_url':u,'discovered_title':clean(a.text_content())})
  log({'at':now(),'kind':'discovery_result','url':u,'count_total':len(items),'response_sha256':req['sha256']})
 (OUT/'discovered-links.json').write_text(json.dumps(list(items.values()),ensure_ascii=False,indent=2), encoding='utf-8')
 # Recent issue first; alternate 2025 history after 2026 depending limit.
 queue=sorted(items.values(),key=lambda x:tuple(map(int,re.search(r'/Y(\d+)/V(\d+)/I(\d+)/(\d+)',x['url']).groups())),reverse=True)
 records=[];failures=[];seen=set()
 existing=OUT/'records.json'
 if existing.exists():
  records=load_json(existing);seen={r['url'] for r in records}
 for item in queue:
  if len(records)>=args.limit:break
  if any(item['url']==x.get('requested_url') for x in records):continue
  try:res=get(item['url'])
  except RuntimeError as e:failures.append({'url':item['url'],'reason':str(e)});break
  if not res:failures.append({'url':item['url'],'reason':'fetch_failed_or_robots'});continue
  b,req=res;req['discovery_url']=item['discovery_url']
  try:r,why=parse_article(b,req)
  except Exception as e:r=None;why='parse_error:'+str(e)
  if not r:
   failures.append({'url':item['url'],'reason':why});log({'at':now(),'url':item['url'],'kind':'rejected_record','reason':why});continue
  if r['url'] in seen:failures.append({'url':item['url'],'reason':'duplicate_canonical_url'});continue
  seen.add(r['url']);r['requested_url']=item['url'];records.append(r)
  tmp=existing.with_suffix('.tmp');tmp.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n', encoding='utf-8');tmp.replace(existing)
  print(json.dumps({'accepted':len(records),'title':r['title'],'published_at':r['published_at']},ensure_ascii=False),flush=True)
 (OUT/'failures.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
 report={'records':len(records),'discovered_links':len(items),'failures':len(failures),'host':'www.society.shu.edu.cn','concurrency':1,'min_interval_seconds':3,'raw_html_persisted':False,'publication_year_counts':{str(y):sum(r['publication_year']==y for r in records) for y in sorted({r['publication_year'] for r in records if r['publication_year']})},'abstract_min_chars':min((r['source_snapshot']['abstract_char_count'] for r in records),default=None),'unique_urls':len(seen),'in_preferred_window':sum(r['within_preferred_window'] for r in records)}
 (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
