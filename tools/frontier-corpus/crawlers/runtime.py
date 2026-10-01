"""Explicit network opt-in and process-wide-per-host locks (Linux/macOS)."""
import fcntl
import urllib.request
import urllib.parse
import tempfile
from pathlib import Path
_LOCKS=[]

def add_run_arguments(parser):
    parser.add_argument('--output', type=Path, required=True, help='Dedicated output directory, not bundled data/')
    parser.add_argument('--allow-network', action='store_true', help='Explicitly enable public-source HTTP requests')

def prepare_run(parser, args, hosts):
    if not args.allow_network:
        parser.error('Network collection is opt-in. Use --allow-network only for an intended live refetch; offline assembly needs no network.')
    output=args.output.resolve()
    bundled=Path(__file__).resolve().parents[1]/'data'
    if output==bundled or bundled in output.parents:
        parser.error('Refusing to overwrite bundled immutable data')
    for host in sorted(hosts):
        lock=open(Path(tempfile.gettempdir())/('qunxue-frontier-'+host+'.lock'),'a')
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close(); parser.error('Another Qunxue collector owns host '+host)
        _LOCKS.append(lock)
    if output.exists() and any(output.iterdir()) and not getattr(args,'resume',False):
        parser.error('Output directory is not empty; choose a fresh directory (journal-only --resume is explicit)')
    output.mkdir(parents=True,exist_ok=True)
    (output/'.gitignore').write_text('*\n!.gitignore\n',encoding='utf-8')
    return output

ALLOWED_HOSTS={'www.society.shu.edu.cn','shjs.ruc.edu.cn','www.zyshgzb.gov.cn'}

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Even same-host redirects can target robots-disallowed paths; never auto-follow.
        raise ValueError('HTTP redirects are disabled; inspect the source before updating its URL')

def validate_public_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError('Only explicit HTTPS source hosts are allowed')
    if parsed.username is not None or parsed.password is not None or parsed.port not in (None,443):
        raise ValueError('Userinfo and nonstandard ports are forbidden')
    return url

def open_public(request,timeout):
    validate_public_url(request.full_url)
    return urllib.request.build_opener(NoRedirectHandler()).open(request,timeout=timeout)

class AccessChallenge(RuntimeError):
    """An explicit access/login challenge requires stopping the source host."""

def assert_no_access_challenge(body):
    # Inspect at the response boundary, including HTTP 200 and robots responses.
    # Conservative signals may stop a source rather than risk retrying a challenge.
    import re
    from html import unescape
    sample=body[:262144].decode('utf-8','replace').lower()
    title_match=re.search(r'<title\b[^>]*>(.*?)</title\s*>',sample,re.S)
    title=unescape(re.sub(r'<[^>]+>',' ',title_match.group(1))) if title_match else ''
    visible=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>',' ',sample,flags=re.S)
    visible=unescape(re.sub(r'<[^>]+>',' ',visible))
    visible=re.sub(r'\s+',' ',visible).strip()
    explicit=['captcha','recaptcha','verify you are human','verify that you are human','请输入验证码','访问过于频繁','安全验证','人机验证','robot check','checking your browser','access denied']
    signal=next((x for x in explicit if x in title),None)
    if not signal and len(visible)<4000:
        signal=next((x for x in explicit if x in visible),None)
    if not signal:
        signal=next((x for x in ['g-recaptcha','h-captcha','cf-chl-','challenge-platform'] if x in sample),None)
    if not signal and re.search(r'<(?:input|iframe)\b[^>]*(?:captcha|recaptcha)',sample):signal='captcha_form'
    login_title=any(x in title for x in ['sign in to continue','login required','authentication required','用户登录','请先登录','请登录'])
    password_form=re.search(r'<input\b[^>]*type\s*=\s*[\"\']?password\b',sample)
    if not signal and (login_title or password_form):signal='login_gate'
    if signal:raise AccessChallenge('Access challenge detected ('+signal+'); stop source host without retry')
