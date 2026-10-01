#!/usr/bin/env python3
"""Conservative historical metadata adapters. No body redistribution or model APIs."""
import argparse
import collections
import datetime as dt
import fcntl
import hashlib
import json
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse as up
import urllib.request
import urllib.robotparser
from pathlib import Path
from lxml import html

ROOT = Path(__file__).resolve().parent
# Reuse the existing production collector's access boundary, without mutating it.
sys.path.insert(0, str(ROOT.parent / 'frontier-corpus' / 'crawlers'))
from runtime import assert_no_access_challenge, NoRedirectHandler
UA = 'QunxueHistoryResearch/0.1 (public metadata audit; no login)'
PARSER_VERSION = 'history-metadata-v1'
HOSTS = {'shxyj.ajcass.com', 'shfzyj.ajcass.com', 'qnyj.ajcass.com',
         'www.cycrc.org.cn', 'www.zyshgzb.gov.cn'}
JOURNALS = {'sociological-studies': 'shxyj.ajcass.com',
            'social-development': 'shfzyj.ajcass.com', 'youth-studies': 'qnyj.ajcass.com'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else
                          json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def text(node):
    return re.sub(r'\s+', ' ', node.text_content()).strip()


def validate_url(url, hosts):
    p = up.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username is not None or p.password is not None or p.port not in (None, 443):
        raise ValueError('URL must use an approved public HTTPS host without credentials')
    return url


def check_access(body):
    assert_no_access_challenge(body)
    sample = body[:262144].decode('utf-8', 'replace').lower()
    if any(s in sample for s in ['please enable javascript and refresh', 'token无效', '请重新登录']):
        raise RuntimeError('Authentication or JavaScript access challenge; stop host')


def publication_date(label):
    m = re.search(r'(20\d{2})[-年](\d{1,2})[-月](\d{1,2})(?:日|\b)', label)
    if m:
        try:
            return dt.date(*map(int, m.groups())).isoformat(), 'day'
        except ValueError:
            return None, 'unknown'
    m = re.search(r'(20\d{2})[-年](\d{1,2})月?', label)
    if m and 1 <= int(m[2]) <= 12:
        return f'{int(m[1]):04d}-{int(m[2]):02d}', 'month'
    return None, 'issue' if re.search(r'20\d{2}.*第?\d+期', label) else 'unknown'


def journal_issues(body, base, start, end):
    rows = {}
    for a in html.fromstring(body.decode('utf-8', 'replace')).xpath('//a[@href]'):
        url = up.urljoin(base, a.get('href'))
        p = up.urlsplit(url)
        q = up.parse_qs(p.query)
        if p.hostname != up.urlsplit(base).hostname or p.path.lower().rstrip('/') != '/magazine':
            continue
        try:
            year, issue = int(q['Year'][0]), int(q['Issue'][0])
        except (KeyError, ValueError):
            continue
        if int(start[:4]) <= year <= int(end[:4]) and issue > 0:
            rows[url] = {'url': url, 'publication_year': year, 'publication_issue': issue}
    return sorted(rows.values(), key=lambda r: (r['publication_year'], r['publication_issue'], r['url']))


def coverage(source, discovered, fetched, *, expected=None, enumeration_complete=False):
    return {'source_id': source, 'expected_count': expected, 'discovered_count': discovered,
            'fetched_count': fetched, 'discovered_unfetched_count': max(0, discovered - fetched),
            'missing_count': None if expected is None else max(0, expected - fetched),
            'enumeration_complete': enumeration_complete,
            'coverage_complete': bool(enumeration_complete and expected is not None and expected > 0 and fetched == expected)}


def newspaper_calendar(body, base, year, start, end):
    payload = json.loads(body.decode('utf-8-sig'))
    rows = {}
    for values in payload.values():
        if not isinstance(values, list):
            continue
        for fragment in values:
            if not isinstance(fragment, str) or not fragment.strip():
                continue
            tree = html.fromstring(fragment)
            m = re.search(r'(\d+)月(\d+)日', text(tree))
            if not m:
                continue
            date = dt.date(year, int(m[1]), int(m[2])).isoformat()
            a = tree if tree.tag == 'a' else next(iter(tree.xpath('.//a[@href]')), None)
            if a is not None and start <= date <= end:
                url = up.urljoin(base, a.get('href'))
                validate_url(url, {up.urlsplit(base).hostname})
                rows[url] = {'url': url, 'published_at': date}
    return sorted(rows.values(), key=lambda r: (r['published_at'], r['url']))


def canonical_id(row):
    doi = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', (row.get('doi') or '').strip(), flags=re.I).lower()
    if doi:
        return 'doi:' + doi
    if row.get('authors'):
        def norm(s):
            return ''.join(c for c in unicodedata.normalize('NFKC', s).casefold() if c.isalnum())
        return 'title-author:' + digest([norm(row['title']), sorted(norm(a) for a in row['authors'])])
    return 'source-url:' + digest([row.get('source_id'), row['url']])


def deduplicate(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        if row.get('abstract_sha256'):
            groups[row['abstract_sha256']].append(row)
    collisions = {r['id'] for group in groups.values() if len({r['title'] for r in group}) > 1 for r in group}
    keep, quarantine, seen = [], [], set()
    for row in rows:
        if row['id'] in collisions:
            quarantine.append(dict(row, quarantine_reason='distinct_titles_share_abstract_hash'))
            continue
        key = canonical_id(row)
        if key not in seen:
            seen.add(key)
            keep.append(dict(row, canonical_study_id=key))
    return keep, quarantine


class Fetcher:
    """Parsed-metadata cache and durable per-host stops; never cache raw bodies."""
    def __init__(self, output, hosts=HOSTS, min_interval=3.1):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.hosts, self.min_interval, self.last, self.robots = hosts, min_interval, {}, {}
        self.stop_file = self.output / 'stopped-hosts.json'
        self.stopped = json.loads(self.stop_file.read_text()) if self.stop_file.exists() else {}
        self.opener = urllib.request.build_opener(NoRedirectHandler())

    def transport(self, url):
        try:
            with self.opener.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=20) as r:
                body = r.read(2_000_001)
                if len(body) > 2_000_000:
                    raise RuntimeError('Oversized response')
                return r.status, dict(r.headers), body
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read(262144)

    def read(self, url, parser, *, robots_probe=False):
        validate_url(url, self.hosts)
        host = up.urlsplit(url).hostname
        cache = self.output / 'cache' / (digest(url) + '.json')
        if cache.exists():
            entry = json.loads(cache.read_text())
            if entry['parser_version'] != PARSER_VERSION or entry['url'] != url or digest(entry['parsed']) != entry['parsed_sha256']:
                raise ValueError('Invalid or incompatible metadata cache')
            return entry['parsed']
        if host in self.stopped:
            raise RuntimeError('Source stopped: ' + self.stopped[host])
        if not robots_probe:
            self.check_robots(host)
            if not self.robots[host].can_fetch(UA, url):
                raise RuntimeError('robots_disallowed')
        delay = self.min_interval
        if host in self.robots:
            delay = max(delay, self.robots[host].crawl_delay(UA) or self.robots[host].crawl_delay('*') or 0)
        time.sleep(max(0, self.last.get(host, 0) + delay - time.monotonic()))
        self.last[host] = time.monotonic()
        entry = {'url': url, 'captured_at': now(), 'parser_version': PARSER_VERSION, 'raw_retained': False}
        try:
            status, headers, body = self.transport(url)
            entry.update(http_status=status, bytes=len(body), response_sha256=digest(body))
            if status in (401, 403, 429) or 300 <= status < 400:
                raise RuntimeError('access_rate_or_redirect_stop_' + str(status))
            check_access(body)
            if status != 200 and not (robots_probe and status in (404, 410)):
                raise RuntimeError('http_' + str(status))
            parsed = parser(body if status == 200 else b'')
            entry.update(parsed=parsed, parsed_sha256=digest(parsed), headers={k:v for k,v in headers.items() if k.lower() in ('content-type', 'x-robots-tag')})
            dump(cache, entry)
            return parsed
        except Exception as e:
            entry['error'] = str(e)
            # Stop on transport uncertainty as well, with distinct reason; no source-ban inference.
            self.stopped[host] = type(e).__name__ + ': ' + str(e)
            dump(self.stop_file, self.stopped)
            raise
        finally:
            with (self.output / 'requests.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def check_robots(self, host):
        if host not in self.robots:
            result = self.read('https://' + host + '/robots.txt', lambda b: {'rules': b.decode('utf-8', 'replace').splitlines()}, robots_probe=True)
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(result['rules'])
            self.robots[host] = rp


def publisher_links(body, base, start, end):
    archives, issues = {}, {}
    for a in html.fromstring(body.decode('utf-8', 'replace')).xpath('//a[@href]'):
        url = up.urljoin(base, a.get('href'))
        p = up.urlsplit(url)
        m = re.match(r'/xsqk/qnyj/qnyj(20\d{2})/', p.path)
        if p.hostname != 'www.cycrc.org.cn' or not m or not int(start[:4]) <= int(m[1]) <= int(end[:4]):
            continue
        if p.path == m[0]:
            archives[url] = url
        elif p.path.endswith('.html'):
            issue = re.search(r'(20\d{2})年?第?(\d{1,2})期', text(a))
            if issue:
                issues[url] = {'url':url, 'title':text(a), 'publication_year':int(issue[1]), 'publication_issue':int(issue[2]), 'published_at':None, 'published_at_precision':'issue'}
    return {'archives':sorted(archives), 'issues':list(issues.values())}


def publisher_issue(body, url):
    tree = html.fromstring(body.decode('utf-8', 'replace'))
    title = text(next(iter(tree.xpath('//h1')), tree))
    m = re.search(r'(20\d{2})年?第?(\d{1,2})期', title)
    if not m:
        raise ValueError('No verified publication issue')
    dates = tree.xpath('//meta[translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="pubdate"]/@content')
    return {'url':url, 'title':title, 'publication_year':int(m[1]), 'publication_issue':int(m[2]),
            'published_at':None, 'published_at_precision':'issue', 'date_basis':'explicit_issue_label',
            'page_uploaded_at':dates[0] if dates else None, 'content_scope':'issue_directory_metadata',
            'body_sha256':digest(body), 'body_retained':False}



def publisher_images(body, base):
    tree = html.fromstring(body.decode('utf-8', 'replace'))
    nodes = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," bookdesc ")]')
    covers = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," xspicScroll-left ")]//li//img/@src')
    groups=[]
    for index,node in enumerate(nodes):
        urls=[]
        for src in node.xpath('.//img/@src'):
            url=up.urljoin(base,src)
            validate_url(url,{'www.cycrc.org.cn'})
            if url not in urls: urls.append(url)
        if urls:
            groups.append({'archive_url':base,'group_index':index,'image_urls':urls,
                           'cover_url':up.urljoin(base,covers[index]) if index<len(covers) else None,
                           'publication_issue':None,'published_at':None,'published_at_precision':'unknown',
                           'content_scope':'image_directory_only','date_basis':'cover_not_yet_verified'})
    return groups



def image_metadata(body):
    import struct
    if len(body)>=24 and body.startswith(b'\x89PNG\r\n\x1a\n'):
        width,height=struct.unpack('>II',body[16:24])
        format='PNG'
    elif body.startswith(b'\xff\xd8\xff'):
        from PIL import Image
        import io
        with Image.open(io.BytesIO(body)) as image:
            width,height=image.size
            format=image.format
    else:
        raise ValueError('Expected public PNG/JPEG directory image, got another response')
    if width<1 or height<1:raise ValueError('Invalid image dimensions')
    return {'sha256':digest(body),'bytes':len(body),'width':width,'height':height,'format':format,
            'content_scope':'directory_image','full_text_verified':False,'raw_retained':False}



def toc_candidates(lines, url):
    # OCR output is a review aid, never promoted to verified article metadata.
    label = ' '.join(str(r.get('text','')) for r in lines)
    m = re.search(r'(20\d{2})年第?(\d{1,2})期',label)
    if not m: raise ValueError('OCR image has no explicit publication issue')
    right = sorted((r for r in lines if r.get('x',0)>0.42),key=lambda r:-r.get('y',0))
    return {'url':url,'publication_year':int(m[1]),'publication_issue':int(m[2]),
            'published_at':None,'published_at_precision':'issue','date_basis':'ocr_explicit_issue_label_requires_review',
            'full_text_verified':False,'verification_status':'review_queue','content_scope':'toc_image_ocr',
            'review_lines':[{'text':r['text'],'confidence':r.get('confidence'), 'x':r.get('x'), 'y':r.get('y')} for r in right],
            'manual_title_verification_required':True}



def parse_tsv(tsv, width, height):
    import csv
    import io
    groups=collections.defaultdict(list)
    # Tesseract text is literal TSV, including standalone quote characters.
    for row in csv.DictReader(io.StringIO(tsv),delimiter='\t',quoting=csv.QUOTE_NONE):
        if row.get('level')=='5' and row.get('text','').strip():
            groups[(row['page_num'],row['block_num'],row['par_num'],row['line_num'])].append(row)
    result=[]
    for words in groups.values():
        left=min(int(w['left']) for w in words)
        top=min(int(w['top']) for w in words)
        result.append({'text':' '.join(w['text'] for w in words),
                       'confidence':min(float(w['conf']) for w in words)/100,
                       'x':left/width,'y':1-top/height})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--allow-network', action='store_true')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--source', choices=['china-youth', 'social-work-news', *JOURNALS], default='china-youth')
    ap.add_argument('--start', default='2025-01-01')
    ap.add_argument('--end', default='2026-10-02')
    ap.add_argument('--max-pages', type=int, default=20)
    args = ap.parse_args()
    if not args.allow_network:
        ap.error('Live collection requires explicit --allow-network')
    if args.max_pages < 1 or args.max_pages > 100:
        ap.error('--max-pages must be 1..100')
    if dt.date.fromisoformat(args.start) > dt.date.fromisoformat(args.end):
        ap.error('Invalid date window')
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()) and not args.resume:
        ap.error('Output is nonempty; use --resume or a new dedicated path')
    repository = ROOT.parents[1]
    # Only the new owned directory or an external run directory may be written.
    if repository in out.parents and ROOT not in out.parents:
        ap.error('Refusing to write existing repository data or code')
    out.mkdir(parents=True, exist_ok=True)
    locks=[]
    host = JOURNALS.get(args.source, 'www.cycrc.org.cn' if args.source == 'china-youth' else 'www.zyshgzb.gov.cn')
    lock = open(Path(tempfile.gettempdir()) / ('qunxue-frontier-' + host + '.lock'), 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error('Another collector owns this source host')
    locks.append(lock)
    fetcher = Fetcher(out, hosts={host})
    records, discovered, errors = [], [], []
    try:
        if args.source in JOURNALS:
            base = 'https://' + host + '/'
            discovered = fetcher.read(base, lambda b: journal_issues(b, base, args.start, args.end))
            dump(out / 'discovered.json', discovered)
            for issue in discovered[:args.max_pages]:
                # Refuse to classify a fetched HTML challenge/empty shell as a readable issue.
                row = fetcher.read(issue['url'], lambda b: publisher_issue(b, issue['url']))
                records.append(row)
        elif args.source == 'china-youth':
            seed = 'https://www.cycrc.org.cn/xsqk/qnyj/zdqs_qn/'
            links = fetcher.read(seed, lambda b: publisher_links(b, seed, args.start, args.end))
            for archive in links['archives'][:args.max_pages]:
                result = fetcher.read(archive, lambda b: {'links':publisher_links(b, archive, args.start, args.end), 'image_groups':publisher_images(b,archive)})
                discovered.extend(result['links']['issues'])
                records.extend(result['image_groups'])
            dump(out / 'discovered.json', discovered)
            for issue in discovered[:args.max_pages]:
                records.append(fetcher.read(issue['url'], lambda b: publisher_issue(b, issue['url'])))
        else:
            base = 'https://www.zyshgzb.gov.cn'
            seed = base + '/459402/459416/461614/index.html'
            years = fetcher.read(seed, lambda b: json.loads(b.decode('utf-8-sig')))
            for year in years:
                if not int(args.start[:4]) <= int(year['title']) <= int(args.end[:4]):
                    continue
                url = up.urljoin(base, year['url'])
                discovered.extend(fetcher.read(url, lambda b: newspaper_calendar(b, base, int(year['title']), args.start, args.end)))
            dump(out / 'discovered.json', discovered)
            # Enumerate all linked issue URLs; article harvesting stays separate from calendar coverage.
        dump(out / 'records.json', records)
    except Exception as e:
        errors.append({'reason':type(e).__name__ + ': ' + str(e), 'source_id':args.source})
    result = coverage(args.source, len(discovered), sum('publication_year' in r for r in records), enumeration_complete=False)
    result['image_group_count'] = sum(r.get('content_scope') == 'image_directory_only' for r in records)
    result.update(window={'start':args.start, 'end':args.end, 'timezone':'Asia/Shanghai'},
                  count_unit='issue_directory', errors=errors, captured_at=now(), bounded_page_limit=args.max_pages)
    dump(out / 'coverage.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
