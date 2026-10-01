#!/usr/bin/env python3
"""Offline checks. Child processes refuse network sockets; no source is fetched."""
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(records):
    return hashlib.sha256(json.dumps(records,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main():
    metadata=json.loads((ROOT/'snapshot.json').read_text(encoding='utf-8'))
    checks=[]
    for relative,expected in metadata['input_files_sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,relative
    checks.append('bundled_input_hashes_match')
    with tempfile.TemporaryDirectory(prefix='qunxue-portability-') as temporary:
        base=Path(temporary);copy=base/'moved'/'tools';cwd=base/'unrelated-cwd';cwd.mkdir()
        shutil.copytree(ROOT,copy,ignore=shutil.ignore_patterns('__pycache__','output','runs','SHA256SUMS'))
        guard=base/'no-network';guard.mkdir()
        (guard/'sitecustomize.py').write_text("import sys\ndef guard(event,args):\n if event.startswith('socket.') and event not in ('socket.__new__',): raise RuntimeError('Network forbidden by offline test: '+event)\nsys.addaudithook(guard)\n", encoding='utf-8')
        env={**os.environ,'PYTHONPATH':str(guard),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'}
        def run(*args):
            return subprocess.run([sys.executable,*map(str,args)],cwd=cwd,env=env,capture_output=True,text=True,timeout=30)
        output=base/'build'/'output'
        assembled=run(copy/'assemble_corpus.py','--output',output)
        assert assembled.returncode==0,assembled.stderr
        data=json.loads((output/'frontier-corpus.json').read_text(encoding='utf-8'))
        assert data['record_count']==201
        assert data['statistics']['stream_counts']=={'practice':63,'research':138}
        assert data['statistics']['unknown_exact_date_excluded_from_months']==16
        assert data['statistics']['dated_in_preferred_window']==113
        assert digest(data['records'])==metadata['canonical_record_payload_sha256']
        checks.extend(['moved_directory_other_cwd_offline_assembly_201','record_payload_matches_original_201','research_138_practice_63','issue_only_16_excluded','recent_day_dated_113'])
        # Re-run from another output dir: payload stable, generated_at is not a snapshot timestamp.
        rerun=run(copy/'assemble_corpus.py','--output',base/'another-build')
        assert rerun.returncode==0,rerun.stderr
        assert json.loads((base/'another-build'/'frontier-corpus-records.json').read_text(encoding='utf-8'))==data['records']
        checks.append('offline_record_payload_repeatable')
        seed=copy/'data/manual-seed-records.json'; seed.rename(seed.with_suffix('.missing'))
        missing=run(copy/'assemble_corpus.py','--output',base/'must-not-exist')
        assert missing.returncode!=0 and 'Missing required input' in missing.stderr
        assert not (base/'must-not-exist').exists()
        seed.with_suffix('.missing').rename(seed)
        checks.append('missing_input_fails_before_output')
        for name in ['collect_society.py','harvest_ruc_journals.py','collect_practice.py']:
            script=copy/'crawlers'/name
            helped=run(script,'--help');assert helped.returncode==0,helped.stderr
            deny_output=base/('denied-'+name)
            denied=run(script,'--output',deny_output)
            assert denied.returncode!=0 and 'opt-in' in denied.stderr,denied.stderr
            assert not deny_output.exists()
        checks.extend(['all_crawler_help_offline','network_gate_fails_before_output'])
        before={str(p.relative_to(copy)) for p in copy.rglob('*')}
        imported=run('-c',"import sys,runpy;sys.path.insert(0,"+repr(str(copy/'crawlers'))+");"+';'.join('runpy.run_path('+repr(str(copy/'crawlers'/name))+')' for name in ['runtime.py','fetch_helper.py','collect_society.py','harvest_ruc_journals.py','collect_practice.py']))
        assert imported.returncode==0,imported.stderr
        after={str(p.relative_to(copy)) for p in copy.rglob('*')}
        assert before==after,(after-before)
        checks.append('crawler_imports_do_not_write_or_fetch')
        # No socket call needed to validate all redirect and URL boundaries.
        safety=run('-c',"""import sys,urllib.request
sys.path.insert(0,"""+repr(str(copy/'crawlers'))+""")
from runtime import validate_public_url,NoRedirectHandler
validate_public_url('https://shjs.ruc.edu.cn/CN/Y2026/V13/I3')
for bad in ['https://localhost/','http://shjs.ruc.edu.cn/','https://shjs.ruc.edu.cn:8443/','https://name@shjs.ruc.edu.cn/','https://evil.example/']:
 try: validate_public_url(bad)
 except ValueError: pass
 else: raise AssertionError(bad)
handler=NoRedirectHandler(); req=urllib.request.Request('https://shjs.ruc.edu.cn/robots.txt')
for target in ['https://shjs.ruc.edu.cn/private','https://localhost/','http://shjs.ruc.edu.cn/']:
 try: handler.redirect_request(req,None,302,'redirect',{},target)
 except ValueError: pass
 else: raise AssertionError(target)
""")
        assert safety.returncode==0,safety.stderr
        checks.append('url_allowlist_and_all_redirects_rejected')
    report={'passed':True,'network_requests':0,'tested_live_refetch':False,'checks':checks,'record_count':201,'runtime':sys.version.split()[0],'validation_scope':'Offline portability, frozen-record equivalence, CLI/network boundaries; no assertion about current source availability.'}
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
