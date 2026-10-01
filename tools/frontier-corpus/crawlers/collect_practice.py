#!/usr/bin/env python3
"""One-time low-rate sampler of public official practice articles.
Re-run: python collect_practice.py --per-month 5
Only 25-character excerpts leave the local audit directory. No LLM or embeddings.
"""
import argparse, json, re, hashlib, collections, datetime
from pathlib import Path
from urllib.parse import urljoin
from lxml import html
from fetch_helper import fetch,init_robots,now,configure
from runtime import add_run_arguments,prepare_run
ROOT=None
AUDIT=None
PACKAGE_ROOT=Path(__file__).resolve().parents[1]
BASE='https://www.zyshgzb.gov.cn'
INDEX=BASE+'/459402/459416/461614/index.html'
WINDOW=('2025-10-01','2026-10-01')
TOPICS={
 '医务社会工作':['医务','医疗','患者','医院','医患'],
 '学校与青少年服务':['学校','校园','青少年','未成年人','儿童','家校','亲子'],
 '老年与照护服务':['养老','老人','老年','银发','照护','助老'],
 '社区治理':['社区','小区','物业','居民','网格','基层治理'],
 '专业社工服务':['社工','社会工作服务','专业社会工作','专业人员'],
 '志愿服务':['志愿','志愿者'],
 '新就业群体服务':['新就业','骑手','外卖','司机','新业态','暖“新”'],
 '社会组织协作':['社会组织','协会','商会'],
 '乡村与基层服务':['乡村','农村','村民','村庄','乡镇'],
 '心理与个案支持':['心理','个案','情绪','危机干预'],
 '困难群体支持':['困境','困难群众','残疾','帮扶','救助'],
 '协商与矛盾调处':['议事','协商','调解','纠纷','矛盾调处'],
}
ACTIONS={
 '个案支持':['个案','危机干预'], '团体活动':['小组工作','小组活动','团体'],
 '需求识别':['需求调查','需求评估','走访','问卷','入户','摸排'],
 '跨机构协作':['联动','协作','联席','转介','资源链接'],
 '人员能力培养':['培训','督导','带教','培养'],
 '志愿力量组织':['志愿者','志愿服务队'], '心理支持':['心理疏导','情绪安抚','心理服务','哀伤辅导'],
 '居民参与':['议事','协商','居民自治','居民参与'],
 '服务资源配置':['购买服务','驻校','驻点','设立','服务站'],
}
EXCLUDE=['全国人民代表大会','中华人民共和国','（大家谈）','（专家','印发','条例','组织法','办法','规定','关于修改','决定','思考','探析','习近平','总书记','国务院新闻','利润增长','标准发布','系列评论','社论','学思践悟','理论视界','会客厅','工作交流','理论研究','记者问','回信','重要讲话','新闻速递','召开','开班','培训班','座谈会','部署','授课','发布','中央文件','全国“两优一先”','全国优秀','风采','学习贯彻','党员论坛','能力提升班']
STRONG=['（工作实践）','社工','社会工作服务','社区','基层治理','志愿','物业','村民','小区','居民','新就业','网格','亲子','养老','帮扶']
def clean(x):return re.sub(r'\s+',' ',x or '').strip()
def cls(tree,name):return tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," '+name+' ")]')
def txt(node):return clean(''.join(node.itertext()))
def normtitle(s):return re.sub(r'[\W_]+','',s)
def dump(name,x):(ROOT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
def article(url,issue_url,index_title,issue_date):
 meta,b=fetch(url)
 if meta['status']!=200:raise ValueError('article_http_'+str(meta['status']))
 tree=html.fromstring(b)
 t=cls(tree,'title'); title=txt(t[0]) if t else ''
 pre=cls(tree,'pre'); sub=cls(tree,'sub')
 title=' '.join([txt(pre[0]) if pre else '',title,txt(sub[0]) if sub else '']).strip()
 if not title:raise ValueError('missing_title')
 info=cls(tree,'article-info'); it=txt(info[0]) if info else ''
 dm=re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',it)
 dates=tree.xpath('//meta[@name="publishdate"]/@content')
 if not dm:raise ValueError('missing_visible_real_publication_date')
 date=f'{int(dm[1]):04d}-{int(dm[2]):02d}-{int(dm[3]):02d}'
 datetime.date.fromisoformat(date)
 if dates and dates[0]!=date:raise ValueError('conflicting_date_metadata')
 if not WINDOW[0]<=date<=WINDOW[1]:raise ValueError('outside_window')
 if date[:7]!=issue_date[:7]:raise ValueError('issue_month_date_mismatch')
 body=cls(tree,'article-context')
 if not body:raise ValueError('missing_readable_body')
 paras=[txt(p) for p in body[0].xpath('.//p') if 'editor' not in p.get('class','').split()]
 paras=[p for p in paras if p and not p.startswith('(责编') and not p.startswith('（责编')]
 body_text='\n'.join(paras)
 if len(body_text)<250:raise ValueError('body_too_short')
 if any(w in body_text[:500] for w in ['请输入验证码','访问过于频繁','安全验证']):raise RuntimeError('access_challenge_stop')
 topics=[(sum(body_text.count(k)+4*title.count(k) for k in keys),topic) for topic,keys in TOPICS.items()]
 topics=[name for score,name in sorted(topics,reverse=True) if score>1][:5]
 if not topics:raise ValueError('no_relevant_social_work_practice_terms')
 actions=[a for a,keys in ACTIONS.items() if any(k in body_text for k in keys)][:5]
 # Score body sentences; choose one short original phrase, maximum 25 Chinese characters.
 chunks=[]
 for i,p in enumerate(paras):
  if len(p)<25 or p.startswith(('编者按','本报','（','截至')):continue
  for chunk in re.split('[。！？；，]',p):
   chunk=chunk.strip('　 ')
   if 12<=len(chunk)<=25:
    score=sum(2 for keys in ACTIONS.values() for k in keys if k in chunk)+sum(1 for keys in TOPICS.values() for k in keys if k in chunk)
    chunks.append((score-i*0.01,chunk,i+1))
 if chunks:_,excerpt,pi=max(chunks)
 else:
  eligible=[(p,i+1) for i,p in enumerate(paras) if len(p)>25 and not p.startswith('编者按')]
  excerpt,pi=eligible[0];excerpt=excerpt[:24]+'…'
 author=cls(tree,'author'); astr=txt(author[0]) if author else ''
 authors=None  # Raw bylines may mix reporters, correspondents and institutions; do not infer names.
 origin=cls(tree,'origin');source=txt(origin[0]).split('来源：')[-1].strip() if origin else '中国社会工作报'
 summary='报道涉及'+('、'.join(topics[:3]))+'；正文可检索的服务或治理做法包括'+('、'.join(actions[:3]) if actions else '地方组织与服务安排')+'。这是机器主题提要，未人工通读或验证成效。'
 cid=re.search(r'-(\d+)\.html',url).group(1)
 genre='practice_column' if '工作实践' in title else ('practitioner_profile' if '人物' in title else ('practice_reflection' if '工作手记' in title else 'practice_news_report'))
 return dict(id='practice-zyshgzb-'+cid,external_id='zyshgzb:'+cid,title=title,authors=authors,author_byline_raw=astr or None,published_at=date,publication_year=int(date[:4]),published_at_precision='day',published_at_display=dm[0],source_display_datetime=it.split('|')[0].strip(),source_name=source,source_publisher='中共中央社会工作部信息宣传中心',hosting_authority='中共中央社会工作部',source_published_at=date,source_date_label='官方新闻正文页显示发布日期',url=url,material_type='official_practice',source_genre=genre,source_scope='official_newspaper_practice',summary=summary,summary_method='deterministic keyword-to-topic mapping, plus a separately capped extractive excerpt; no LLM',short_excerpt=excerpt,topics=topics,practice_actions_detected=actions,research_question=None,methods=None,data=None,sample=None,findings=None,limitations=None,missing_reasons=dict(authors='作者栏可能混合角色与机构，未结构化核验；可用原始署名保存在author_byline_raw。',**{k:'本轮仅机器采集公开实践报道并提取主题；未人工全文核验，不推断学术研究或成效结论。' for k in ['research_question','methods','data','sample','findings','limitations']}),verification_status='practice_signal',verification_note='已获取官方公开HTML正文，程序核对题名、可见发布日期与正文长度；非人工逐篇全文审读。',evidence_scope='public_practice_body_algorithmically_parsed',discovered_at=meta['captured_at'],discovered_at_precision='second',evidence=[dict(snippet=None,excerpt_pointer='short_excerpt',locator='div.article-context p; paragraph '+str(pi),supports=['practice_actions_detected','summary'],url=url)],source_snapshot=dict(captured_at=meta['captured_at'],kind='minimal_hash_evidence_with_local_audit_reference',robots_directives=meta.get('robots_directives',[]),local_audit_reference=meta.get('snapshot'),retention=meta.get('retention','local_only'),sha256=meta['sha256'],http_status=meta['status'],export_note='本地审计快照，不用于公开分发全文；产品仅保留<=25字摘录与算法主题提要'),body_char_count=len(body_text),body_sha256=hashlib.sha256(body_text.encode()).hexdigest(),copyright_export_policy='No full body exported. One short excerpt <=25 characters; keyword-derived topics and non-evaluative summary only.',editorial_caveat='媒体/实施方经验报道；可能含自报规模或成效，未作独立核验，不是同行评审或因果证据。',recency_basis='正文可见发布日期，与meta publishdate交叉核对；不以采集时间代替出版日期。',within_preferred_window=True,source_file='practice-records.json',ingestion_note='一次性公开内容采集；无embedding/付费LLM；机器提取须人工复核后才可用于实质结论。',sampling=dict(issue_url=issue_url,issue_date=issue_date,index_title=index_title,strategy='deterministic monthly quota; topical title filter; newest issue first',probability_sample=False))
def main():
 global ROOT,AUDIT
 ap=argparse.ArgumentParser(description='Fixed 2025-10..2026-09 monthly quota recipe, as of 2026-10-01')
 add_run_arguments(ap);ap.add_argument('--per-month',type=int,default=5)
 ap.add_argument('--seed',type=Path,default=PACKAGE_ROOT/'data/manual-seed-records.json')
 ap.add_argument('--exclusions',type=Path,default=PACKAGE_ROOT/'data/practice/reviewed-exclusions.json')
 args=ap.parse_args()
 if not args.seed.is_file() or not args.exclusions.is_file():ap.error('Required seed/exclusion input file is missing')
 ROOT=prepare_run(ap,args,['www.zyshgzb.gov.cn']);configure(ROOT);AUDIT=ROOT/'local-audit'
 init_robots();m,b=fetch(INDEX);years=json.loads(b.decode('utf-8-sig'))
 months=collections.defaultdict(list)
 for y in years:
  if y['title'] not in ('2025','2026'):continue
  ym,yb=fetch(urljoin(BASE,y['url']));data=json.loads(yb.decode('utf-8-sig'))
  for vals in data.values():
   if not isinstance(vals,list):continue
   for s in vals:
    if not isinstance(s,str) or not s.strip():continue
    node=html.fromstring(s);md=re.search(r'(\d+)月(\d+)日',txt(node))
    if not md:continue
    date=f"{y['title']}-{int(md[1]):02d}-{int(md[2]):02d}"
    if WINDOW[0]<=date<WINDOW[1]:months[date[:7]].append((date,urljoin(BASE,node.get('href'))))
 dump('discovered-issues.json',dict(months))
 records=[];failures=[];seentitles=set();seenbodies=set();seenurls=set();candidates=[]
 reviews=json.loads(args.exclusions.read_text(encoding='utf-8'))
 existing=args.seed
 if existing.exists():
  for r in json.loads(existing.read_text(encoding='utf-8')):
   seenurls.add(r['url']);seentitles.add(normtitle(r['title']))
 counts={}
 # Distribute quotas across all months, rather than drawing all from recent issues.
 for month in sorted(months):
  count=0
  for issue_date,issue_url in sorted(set(months[month]),reverse=True)[:6]:
   im,ib=fetch(issue_url)
   if im['status']!=200:
    failures.append(dict(url=issue_url,reason='issue_http_'+str(im['status'])));continue
   tree=html.fromstring(ib);links=[]
   for a in tree.xpath('//a[@href]'):
    href=a.get('href','').strip();title=txt(a)
    if not re.search(r'/n1/20\d{2}/\d{4}/c\d+-\d+\.html',href):continue
    if any(w in title for w in EXCLUDE):continue
    score=sum(3 if w=='（工作实践）' else 1 for w in STRONG if w in title)
    if score<1:continue
    url=urljoin(BASE,href)
    if url in seenurls or normtitle(title) in seentitles:continue
    links.append((-score,url,title))
   for _,url,title in sorted(set(links)):
    if count>=args.per_month:break
    seenurls.add(url);candidates.append(dict(url=url,title=title,issue_date=issue_date,issue_url=issue_url))
    if url in reviews:
     failures.append(dict(url=url,title=title,reason=reviews[url]['reason'],exclusion_method='editorial_spot_check'));continue
    try:r=article(url,issue_url,title,issue_date)
    except ValueError as e:
     failures.append(dict(url=url,title=title,reason=str(e)));dump('failures.json',failures);continue
    except Exception as e:
     failures.append(dict(url=url,title=title,reason=str(e)));dump('failures.json',failures);raise
    nt=normtitle(r['title'])
    if nt in seentitles or r['body_sha256'] in seenbodies:
     failures.append(dict(url=url,title=title,reason='duplicate_title_or_body'));continue
    records.append(r);seentitles.add(nt);seenbodies.add(r['body_sha256']);count+=1
    dump('practice-records.json',records);dump('candidates.json',candidates);dump('failures.json',failures)
    print(f"ACCEPT {len(records)} {month} {count}/{args.per_month} {r['title']}",flush=True)
   if count>=args.per_month:break
  counts[month]=count
  dump('progress.json',dict(month_counts=counts,total=len(records),updated_at=now()))
 report=dict(total=len(records),month_counts=counts,window=WINDOW,domains=['www.zyshgzb.gov.cn'],failures=len(failures),completed_at=now(),sampling='Nonprobability monthly quota sample; title-keyword selection. Counts do not represent publication prevalence or social outcomes.',concurrency_per_domain=1,minimum_request_interval_seconds=3.1,requests=sum(1 for _ in (AUDIT/'requests.jsonl').open()),source_snapshots_local_only=True)
 dump('report.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
