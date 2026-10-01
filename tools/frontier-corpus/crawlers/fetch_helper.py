from runtime import open_public,AccessChallenge,assert_no_access_challenge
import urllib.request, urllib.error, urllib.robotparser, json, hashlib, time, datetime, re
from lxml import html
from pathlib import Path
from urllib.parse import urlparse
ROOT=None
AUDIT=None
SNAP=None

def configure(output):
 global ROOT,AUDIT,SNAP,last,robot,stopped
 ROOT=Path(output);AUDIT=ROOT/'local-audit';AUDIT.mkdir(parents=True,exist_ok=True)
 SNAP=AUDIT/'snapshots'
 last=0;robot=None;stopped=False

UA='QunxueResearchSampler/1.0 (one-time public social-work metadata audit; no login)'
last=0
robot=None
stopped=False

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url,robots=False):
 global last,robot,stopped
 if stopped:raise RuntimeError('domain stopped by response policy')
 if urlparse(url).hostname!='www.zyshgzb.gov.cn':raise ValueError('unapproved external domain')
 key=hashlib.sha256(url.encode()).hexdigest()
 meta=AUDIT/(key+'.json')
 if not robots:
  if robot is None: init_robots()
  if not robot.can_fetch(UA,url):raise RuntimeError('robots disallow '+url)
 for attempt in range(3):
  time.sleep(max(0,max(3.1,(robot.crawl_delay(UA) or robot.crawl_delay('*') or 0) if robot else 0)-(time.monotonic()-last)))
  started=now();last=time.monotonic(); status=None;data=b'';headers={};error=None
  try:
   r=open_public(urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,text/plain;q=0.9,*/*;q=0.1'}),timeout=35)
   status=r.status;data=r.read(5_000_001); headers=dict(r.headers);final=r.url
   assert_no_access_challenge(data)
  except AccessChallenge as e:
   stopped=True
   with (AUDIT/'requests.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'url':url,'captured_at':started,'status':status,'outcome':'access_challenge_stop','error':str(e)},ensure_ascii=False)+'\n')
   raise
  except urllib.error.HTTPError as e:
   status=e.code;data=e.read();headers=dict(e.headers);final=url;error=str(e)
  except Exception as e:
   error=type(e).__name__+': '+str(e);final=url
  m=dict(url=url,final_url=final,captured_at=started,status=status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),attempt=attempt+1,error=error)
  with (AUDIT/'requests.jsonl').open('a') as f:f.write(json.dumps(m,ensure_ascii=False)+'\n')
  if status in (401,403,429):
   stopped=True;raise RuntimeError('domain stop on access/rate limit '+str(status))
  if status in (200,404,410):
   name=key+('.html' if 'html' in headers.get('Content-Type','') else '.txt');m['snapshot']=name
   directives=[v for k,v in headers.items() if k.lower()=='x-robots-tag']
   try:
    page=html.fromstring(data)
    directives+=page.xpath('//meta[translate(@name,"ROBOTS","robots")="robots"]/@content')
   except Exception:pass
   m['robots_directives']=directives
   noarchive=any('noarchive' in d.lower() for d in directives)
   m['retention']='metadata_hash_only';m['snapshot']=None
   meta.write_text(json.dumps(m,ensure_ascii=False,indent=2), encoding='utf-8');return m,data
  time.sleep(10*(2**attempt))
 stopped=True;raise RuntimeError('stop after 3 transient errors '+url+' '+str(error))

def init_robots():
 global robot
 m,b=fetch('https://www.zyshgzb.gov.cn/robots.txt',True)
 robot=urllib.robotparser.RobotFileParser()
 if m['status'] in (404,410):robot.parse([]);note='No robots.txt published (HTTP '+str(m['status'])+'); ordinary low-rate public access only'
 else:
  robot.parse(b.decode('utf-8','replace').splitlines());note='Parsed robot rules for explicit research user-agent'
 (AUDIT/'robots-check.json').write_text(json.dumps(dict(url=m['url'],status=m['status'],checked_at=m['captured_at'],sha256=m['sha256'],note=note),ensure_ascii=False,indent=2), encoding='utf-8')
 return robot
if __name__=='__main__':
 raise SystemExit('Helper module. Run collect_practice.py --help instead.')
