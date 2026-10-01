#!/usr/bin/env python3
"""Polite one-off public RUC journal abstract harvester. No keys, LLMs, login or PDF.
Requires Python 3 and lxml. Noarchive responses are parsed only in memory.
Example: python harvest_ruc_journals.py --target 100 --output ./run-20261001
"""
from runtime import add_run_arguments,prepare_run,open_public,AccessChallenge,assert_no_access_challenge
import argparse, collections, datetime as dt, hashlib, json, pathlib, random, re, time
import urllib.request, urllib.error, urllib.parse, urllib.robotparser
from lxml import html
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from json_shards import load_json

UA = 'QunxueResearchBot/0.1 (one-time public academic metadata research; rate-limited)'
TODAY = dt.date(2026, 10, 1)
WINDOW_START = dt.date(2025, 10, 1)
SOURCES = {
    'shjs.ruc.edu.cn': {'name': '社会建设', 'publisher': '《社会建设》编辑部 / 中国人民大学', 'code': 'shjs'},
}
TOPICS = {
    '社会工作': ['社会工作', '社会工作者', '社工'],
    '社会治理': ['社会治理', '社区治理', '基层治理', '数字治理', '政社关系'],
    '社会政策与保障': ['社会政策', '社会保障', '社会救助', '福利', '低保'],
    '老龄化与照护': ['老龄', '养老', '老年', '照护', '长期护理'],
    '儿童与青少年': ['儿童', '青少年', '未成年'],
    '家庭与生育': ['家庭', '生育', '婚姻', '夫妻', '代际'],
    '数字社会与技术': ['数智', '数字', '算法', '人工智能', '互联网', '平台'],
    '劳动与就业': ['劳动', '就业', '工作满意度', '职业流动'],
    '乡村与城乡': ['乡村', '农村', '城乡', '乡镇'],
    '社会组织与慈善': ['社会组织', '慈善', '公益', '志愿'],
    '教育与社会分层': ['教育', '社会分层', '阶层', '社会流动', '人力资本'],
    '贫困与不平等': ['贫困', '不平等', '低收入', '共同富裕'],
    '健康与医疗': ['健康', '医疗', '抑郁', '精神卫生'],
    '社会理论与方法': ['社会理论', '社会学理论', '理论建构', '类型学', '研究方法'],
}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
def sha(data): return hashlib.sha256(data).hexdigest()
def norm(s): return re.sub(r'\s+', ' ', s or '').strip()
def txt(nodes): return norm(' '.join(n.text_content() if hasattr(n, 'text_content') else str(n) for n in nodes))
def cl(name): return "contains(concat(' ',normalize-space(@class),' '),' %s ')" % name

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

class StopDomain(Exception): pass

class Harvester:
    def __init__(self, output):
        self.out = pathlib.Path(output); self.out.mkdir(parents=True, exist_ok=True)
        self.last = {}; self.robots = {}; self.stopped = set(); self.records = []
        self.requests = []; self.failures = []; self.manifest = []; self.issues = []; self.rejected = []; self.duplicates = []
        (self.out / '.gitignore').write_text('raw/\n__pycache__/\n', encoding='utf-8')

    def log(self, entry, failure=False):
        self.requests.append(entry)
        with (self.out / 'requests.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        if failure:
            self.failures.append(entry)
            with (self.out / 'failures.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def request(self, url, kind='html', robots_probe=False):
        host = urllib.parse.urlparse(url).hostname
        if host not in SOURCES: raise StopDomain('Off-allowlist host')
        if host in self.stopped: raise StopDomain('Domain stopped')
        if not robots_probe and (host not in self.robots or not self.robots[host].can_fetch(UA, url)):
            self.log({'at': now(), 'url': url, 'status': 'robots_denied_or_unknown'}, True)
            raise StopDomain('robots denied or unknown')
        for attempt in range(1, 3):
            delay = random.uniform(2.0, 5.0)
            parser = self.robots.get(host)
            if parser:
                delay = max(delay, parser.crawl_delay(UA) or parser.crawl_delay('*') or 0)
            time.sleep(max(0, self.last.get(host, 0) + delay - time.monotonic()))
            started = now(); self.last[host] = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,text/plain;q=0.9,*/*;q=0.1'})
                # Default TLS verification, proxy and network environment are preserved.
                with open_public(req, timeout=35) as response:
                    final = response.geturl()
                    if urllib.parse.urlparse(final).hostname != host:
                        raise StopDomain('Cross-domain redirect; no further crawl')
                    body = response.read(5_000_001)
                    if len(body) > 5_000_000: raise StopDomain('Oversized response')
                    status = response.status
                    headers = {k.lower(): v for k, v in response.headers.items()}
                assert_no_access_challenge(body)
                tree = None
                meta = []
                if kind == 'html':
                    tree = html.fromstring(body)
                    meta = tree.xpath('//meta[translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="robots"]/@content')
                    title = txt(tree.xpath('//title')).lower()
                    if any(x in title for x in ['captcha', 'access denied', '验证', '安全检查', 'robot check']):
                        raise StopDomain('Captcha or access-control page detected')
                directives = ','.join(meta + [headers.get('x-robots-tag', '')]).lower()
                entry = {'requested_at': started, 'completed_at': now(), 'url': url, 'final_url': final,
                         'kind': kind, 'attempt': attempt, 'http_status': status, 'bytes': len(body),
                         'response_sha256': sha(body), 'content_type': headers.get('content-type'),
                         'x_robots_tag': headers.get('x-robots-tag'), 'meta_robots': meta,
                         'noarchive': 'noarchive' in directives, 'raw_retained': False,
                         'user_agent': UA, 'requested_delay_seconds': round(delay, 3)}
                if robots_probe:
                    path = self.out / (host + '-robots.txt'); path.write_bytes(body)
                    entry['robots_snapshot_file'] = path.name
                self.log(entry); self.manifest.append(entry.copy())
                return body, tree, entry
            except urllib.error.HTTPError as e:
                entry = {'requested_at': started, 'completed_at': now(), 'url': url, 'attempt': attempt,
                         'http_status': e.code, 'error': str(e), 'kind': kind}
                self.log(entry, True)
                if e.code in (401, 403, 429):
                    self.stopped.add(host); raise StopDomain('Authentication/access/rate limit; stop')
                if robots_probe and e.code in (404, 410):
                    raise StopDomain('Robots absent; conservative run does not infer permission')
                if e.code >= 500 and attempt == 1:
                    time.sleep(15); continue
                if robots_probe or e.code >= 500: self.stopped.add(host)
                raise StopDomain(str(e))
            except AccessChallenge as e:
                self.log({'at':now(),'url':url,'attempt':attempt,'outcome':'access_challenge_stop','error':str(e)},True)
                self.stopped.add(host);raise StopDomain(str(e))
            except StopDomain as e:
                self.log({'at': now(), 'url': url, 'attempt': attempt, 'error': str(e)}, True)
                self.stopped.add(host); raise
            except Exception as e:
                self.log({'at': now(), 'url': url, 'attempt': attempt, 'error': type(e).__name__ + ': ' + str(e)}, True)
                if attempt == 1: time.sleep(15); continue
                self.stopped.add(host); raise StopDomain('Repeated transport failure')

    def check_robots(self, host):
        body, _, meta = self.request('https://' + host + '/robots.txt', kind='robots', robots_probe=True)
        parser = urllib.robotparser.RobotFileParser(); parser.parse(body.decode('utf-8', errors='replace').splitlines())
        self.robots[host] = parser
        if not parser.can_fetch(UA, 'https://' + host + '/CN/archive_by_years'):
            self.stopped.add(host); raise StopDomain('Archive forbidden by robots')

    def parse_issue(self, host, url, tree, response):
        config = SOURCES[host]
        issue_parts = re.search(r'/Y(\d{4})/V(\d+)/I(\d+)$', url)
        if not issue_parts: return []
        year, volume, issue = map(int, issue_parts.groups())
        page_text = txt(tree.xpath('//body'))
        dated = re.search(r'刊出日期[：:]\s*(\d{4}-\d{1,2}-\d{1,2})', page_text)
        if not dated: dated = re.search(r'出版日期[：:]\s*(\d{4}-\d{1,2}-\d{1,2})', page_text)
        published = None
        if dated:
            y, m, d = map(int, dated.group(1).split('-')); published = dt.date(y, m, d).isoformat()
        if published and published > TODAY.isoformat():
            self.rejected.append({'url': url, 'reason': 'Future issue date', 'published_at': published}); return []
        output = []
        for node in tree.xpath('//li[starts-with(@id,"art")]'):
            title_nodes = node.xpath('.//*[' + cl('j-title-1') + ']/a')
            abstract_nodes = node.xpath('.//*[' + cl('j-abstract') + ']')
            title = txt(title_nodes); abstract = txt(abstract_nodes)
            article_id = node.get('id', '').removeprefix('art')
            if not title or len(abstract) < 80 or re.search(r'^(目录|封面|稿约|征稿|征订|投稿|更正|勘误)', title):
                self.rejected.append({'url': url, 'article_id': article_id, 'title': title,
                                      'abstract_char_count': len(abstract), 'reason': 'No substantial research abstract or non-research notice'})
                continue
            canonical = urllib.parse.urljoin(url, title_nodes[0].get('href', ''))
            author_text = txt(node.xpath('.//*[' + cl('j-author') + ']'))
            authors = [a.strip() for a in re.split(r'[、,，;；]+', author_text) if a.strip()] or None
            citation = txt(node.xpath('.//*[' + cl('j-volumn') + ']'))
            pagem = re.search(r':\s*([\d\-–—]+)', citation)
            category = txt(node.xpath('.//*[' + cl('j-column') + ']')) or None
            all_text = title + ' ' + abstract
            keyword_hits = {topic: [term for term in terms if term in all_text] for topic, terms in TOPICS.items()}
            keyword_hits = {k: v for k, v in keyword_hits.items() if v}
            excerpt = abstract[:22]
            snapshot = {'captured_at': response['completed_at'], 'kind': 'response_hash_and_minimal_metadata',
                        'source_url': url, 'response_sha256': response['response_sha256'], 'response_bytes': response['bytes'],
                        'raw_retained': response['raw_retained'], 'noarchive': response['noarchive'],
                        'meta_robots': response['meta_robots'], 'x_robots_tag': response['x_robots_tag'],
                        'manifest_file': 'response-manifest.json',
                        'note': 'Noarchive页面仅在内存解析；未保留完整HTML或完整摘要。摘要哈希仅证明本次解析内容身份，不代表全文复核。'}
            if response.get('raw_snapshot_file'): snapshot['raw_snapshot_file'] = response['raw_snapshot_file']
            r = {
                'id': 'research-' + config['code'] + '-' + str(year) + '-' + article_id,
                'external_id': host + ':article:' + article_id,
                'title': title, 'authors': authors, 'author_text': author_text or None,
                'source_name': config['name'], 'source_publisher': config['publisher'],
                'url': canonical, 'canonical_url': canonical, 'evidence_url': url,
                'source_relationship': 'original_journal_issue_page_with_embedded_complete_abstract',
                'source_scope': 'official_journal_issue_abstract',
                'article_url_individually_fetched': False,
                'published_at': published, 'published_at_precision': 'day' if published else 'issue',
                'published_at_display': published or f'{year}年第{issue}期',
                'publication_year': year, 'publication_volume': volume, 'publication_issue': issue,
                'publication_pages': pagem.group(1) if pagem else None,
                'publication_date_source': 'issue_page_explicit_print_publication_label' if published else 'issue_citation_only',
                'date_source': url, 'date_locator': dated.group(0) if dated else citation,
                'source_published_at': None, 'source_date_label': '网页上线日期未核实；未用抓取日代替发表日',
                'material_type': 'research_abstract', 'summary': None, 'research_question': None,
                'methods': None, 'data': None, 'sample': None, 'findings': None, 'limitations': None,
                'topics': list(keyword_hits), 'topic_keyword_hits': keyword_hits,
                'topics_method': 'algorithm_dictionary_keyword_match_on_title_and_read_abstract_unreviewed',
                'journal_section': category, 'abstract_char_count': len(abstract),
                'abstract_sha256': sha(abstract.encode('utf-8')), 'abstract_normalization': 'Unicode text, whitespace collapsed to one ASCII space, stripped',
                'abstract_read_status': 'complete_embedded_abstract_read', 'algorithm_harvested': True,
                'human_full_text_reviewed': False, 'verification_status': 'lead_only',
                'verification_note': '算法实际读取期刊原站期次页中的题名、作者、出版日期和完整摘要；逐篇链接未另行访问，未读论文全文，未人工全文审读。仅作待核查线索。',
                'evidence_scope': 'official_issue_embedded_abstract_only',
                'evidence': [
                    {'snippet': excerpt, 'locator': '#' + node.get('id') + ' .j-abstract / 前22个Unicode字符',
                     'url': url, 'supports': ['abstract_read_status', 'title_abstract_keyword_lead']},
                    {'snippet': None, 'locator': '#' + node.get('id') + ' .j-title-1, .j-author, .j-volumn',
                     'url': url, 'supports': ['title', 'authors', 'publication_year', 'publication_issue', 'publication_pages']}
                ],
                'source_snapshot': snapshot, 'discovered_at': response['requested_at'], 'discovered_at_precision': 'second',
                'within_preferred_window': WINDOW_START.isoformat() <= published <= TODAY.isoformat() if published else None,
                'recency_basis': '页面明确刊出日期；2025-10-01至2026-10-01为优先窗口；更早资料作历史基线',
                'missing_reasons': {
                    'summary': '批采未生成人工释义摘要，避免冒充精读。',
                    'research_question': '未逐篇人工编码。', 'methods': '未逐篇人工核验与结构化方法。',
                    'data': '未逐篇人工核验与结构化数据。', 'sample': '未逐篇人工核验与结构化样本。',
                    'findings': '未逐篇人工核验论证与研究发现。', 'limitations': '未阅读全文。',
                    'source_published_at': '期次页未单独确认网页上线日期。'
                },
                'ingestion_note': '一次性算法抓取；无付费LLM/embedding/API key；仅元数据、词表命中和短摘录。',
                'editorial_caveat': '来源与期次覆盖不均，关键词只用于此采集样本内描述；不得解释为学科总体趋势、因果证据或质量排序。'
            }
            if not published: r['missing_reasons']['published_at'] = '页面无明确刊出/出版日期，保留期次精度。'
            output.append(r)
        self.issues.append({'url': url, 'source_name': config['name'], 'year': year, 'volume': volume,
                            'issue': issue, 'published_at': published, 'included_records': len(output),
                            'response_sha256': response['response_sha256']})
        return output

    def harvest(self, host, target):
        self.check_robots(host)
        url = 'https://' + host + '/CN/archive_by_years'
        _, tree, response = self.request(url)
        discovered = set()
        for href in tree.xpath('//a/@href'):
            u = urllib.parse.urljoin(url, href)
            m = re.search(r'^https://' + re.escape(host) + r'/CN/Y(202[456])/V(\d+)/I(\d+)$', u)
            if m: discovered.add((int(m.group(1)), int(m.group(3)), u))
        dump(self.out / (host + '-discovered-issues.json'), {'archive_url': url, 'archive_response_sha256': response['response_sha256'],
            'discovered_at': now(), 'issues': [u for _, _, u in sorted(discovered, reverse=True)]})
        if not discovered: raise StopDomain('No observed archive issue URLs')
        for _, _, u in sorted(discovered, reverse=True):
            if len(self.write_outputs()[0]) >= target: break
            if any(previous['url'] == u for previous in self.issues): continue
            try:
                _, page, meta = self.request(u)
                self.records.extend(self.parse_issue(host, u, page, meta))
                print(json.dumps({'issue': u, 'records_total': len(self.records)}, ensure_ascii=False), flush=True)
                self.write_outputs()
            except StopDomain:
                if host in self.stopped: break

    def write_outputs(self):
        kept = []; seen_url = {}; seen_title = {}; duplicates = []
        abstract_groups = collections.defaultdict(list)
        for record in self.records:
            abstract_groups[record['abstract_sha256']].append(record)
        collision_hashes = {digest for digest, group in abstract_groups.items() if len({x['title'] for x in group}) > 1}
        quarantined = []
        for r in self.records:
            if r['abstract_sha256'] in collision_hashes:
                quarantined.append({'reason': 'Identical abstract for distinct titles; quarantine all affected records pending source-level review', 'record': r})
                continue
            key = re.sub(r'[^\w\u4e00-\u9fff]', '', r['title']).lower()
            older = seen_url.get(r['url']) or seen_title.get(key)
            if older:
                duplicates.append({'kept': older['id'], 'removed': r['id'], 'reason': 'canonical URL or normalized title duplicate'})
            else:
                kept.append(r); seen_url[r['url']] = r; seen_title[key] = r
        dump(self.out / 'records.json', kept)
        dump(self.out / 'quarantined-records.json', quarantined)
        dump(self.out / 'response-manifest.json', self.manifest)
        coverage = [{**item, 'parsed_readable_records': item.get('parsed_readable_records', item['included_records']),
                     'included_records': sum(r['evidence_url'] == item['url'] for r in kept)} for item in self.issues]
        dump(self.out / 'issue-coverage.json', coverage)
        dump(self.out / 'rejected-records.json', self.rejected)
        dump(self.out / 'dedup-report.json', {'before': len(self.records), 'after': len(kept), 'removed': duplicates, 'quarantined_abstract_collisions': [{'id': x['record']['id'], 'reason': x['reason']} for x in quarantined],
                                             'normalization': 'canonical URL exact; title alphanumeric/CJK Unicode normalized punctuation removal'})
        report = {'generated_at': now(), 'algorithm_harvested': True, 'human_full_text_reviewed': False,
                  'records_count': len(kept), 'quarantined_count': len(quarantined), 'sources': dict(collections.Counter(r['source_name'] for r in kept)),
                  'years': dict(collections.Counter(str(r['publication_year']) for r in kept)),
                  'date_precision': dict(collections.Counter(r['published_at_precision'] for r in kept)),
                  'preferred_window_count': sum(r['within_preferred_window'] is True for r in kept),
                  'historical_baseline_count': sum(r['within_preferred_window'] is False for r in kept),
                  'abstract_char_count_min': min((r['abstract_char_count'] for r in kept), default=None),
                  'abstract_char_count_max': max((r['abstract_char_count'] for r in kept), default=None),
                  'max_exported_snippet_characters': max((len(e['snippet'] or '') for r in kept for e in r['evidence']), default=0),
                  'full_abstracts_exported': 0, 'stopped_domains': sorted(self.stopped),
                  'request_count_logged': len(self.requests), 'failure_count_logged': len(self.failures),
                  'robots_policy': 'robots first; allowlist; fail-closed on unavailable/disallow; no restriction bypass',
                  'fetch_policy': 'single sequential worker; 2–5 seconds minimum spacing; one retry after 15 second backoff for transport/5xx; stop on 401/403/429/challenge',
                  'raw_policy': 'Respect meta robots and X-Robots-Tag; noarchive page bodies only processed in memory; persist hash/minimal metadata',
                  'coverage_limitations': ['Newest observed archive links first, ending after a complete issue once target reached.',
                                           'Publication dates are explicit issue 刊出日期/出版日期, not citation_date, ingest date or search dates.',
                                           'Canonical article URLs are publisher links; evidence actually read at issue page.',
                                           'Convenience sample from selected accessible journals; no claim to represent all sociology or social work research.']}
        dump(self.out / 'harvest-report.json', report)
        return kept, report


def main():
    ap = argparse.ArgumentParser(description='Fixed 2026-10-01 sample recipe; observed archive years 2024-2026')
    add_run_arguments(ap)
    ap.add_argument('--target', type=int, default=100)
    ap.add_argument('--hosts', nargs='+', choices=list(SOURCES), default=['shjs.ruc.edu.cn'])
    ap.add_argument('--resume', action='store_true', help='Resume from checkpoint; fresh robots read still required')
    args = ap.parse_args(); output=prepare_run(ap,args,args.hosts); h = Harvester(output)
    if args.resume and (h.out / 'records.json').exists():
        h.records = load_json(h.out / 'records.json')
        if (h.out / 'quarantined-records.json').exists():
            h.records.extend(x['record'] for x in json.loads((h.out / 'quarantined-records.json').read_text(encoding='utf-8')))
        for attr, filename in [('manifest', 'response-manifest.json'), ('issues', 'issue-coverage.json'), ('rejected', 'rejected-records.json')]:
            if (h.out / filename).exists(): setattr(h, attr, json.loads((h.out / filename).read_text(encoding='utf-8')))
        for attr, filename in [('requests', 'requests.jsonl'), ('failures', 'failures.jsonl')]:
            if (h.out / filename).exists(): setattr(h, attr, [json.loads(line) for line in (h.out / filename).read_text(encoding='utf-8').splitlines() if line.strip()])
    for host in args.hosts:
        try: h.harvest(host, args.target)
        except StopDomain as e: print(json.dumps({'domain': host, 'stopped': str(e)}, ensure_ascii=False), flush=True)
    _, report = h.write_outputs(); print(json.dumps(report, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
