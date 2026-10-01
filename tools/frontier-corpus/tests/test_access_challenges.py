#!/usr/bin/env python3
"""Offline HTTP-200 challenge mocks; never open a network connection."""
import sys,json,tempfile,urllib.robotparser
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'crawlers'))
from runtime import AccessChallenge,assert_no_access_challenge
import collect_society as society
import fetch_helper as practice
import harvest_ruc_journals as journals

def block_network(event,args):
    if event.startswith('socket.') and event!='socket.__new__':raise RuntimeError('Network forbidden in offline challenge test')
sys.addaudithook(block_network)

class Response:
    status=200
    headers={'Content-Type':'text/html; charset=utf-8'}
    def __init__(self,body,url):self.body=body;self.url=url
    def read(self,n=-1):return self.body if n<0 else self.body[:n]
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):return False

def allow_robots():
    robots=urllib.robotparser.RobotFileParser();robots.parse(['User-agent: *','Allow: /']);return robots

def expect_stop(call):
    try:call()
    except (AccessChallenge,journals.StopDomain,RuntimeError):return
    raise AssertionError('Challenge failed to stop source host')

def main():
    payloads=[b'<html><body>captcha</body></html>',b'<html><body>recaptcha</body></html>',b'<html><body>verify you are human</body></html>', '<html><body>请输入验证码</body></html>'.encode(), '<html><body>访问过于频繁</body></html>'.encode(), '<html><body>安全验证</body></html>'.encode(), '<html><title>用户登录</title><input type="password"></html>'.encode(),b'<html><script src="/challenge-platform/check.js"></script></html>']
    assertions=0
    for index,body in enumerate(payloads):
        with tempfile.TemporaryDirectory(prefix='qunxue-challenge-') as tmp:
            root=Path(tmp)
            society.OUT=root;society.LOG=root/'society.jsonl';society.stopped=False;society.robots_ready=True;society.rp=allow_robots()
            url='https://www.society.shu.edu.cn/CN/example'
            with patch.object(society,'open_public',return_value=Response(body,url)) as opener,patch.object(society.time,'sleep'):
                expect_stop(lambda:society.get(url));assert society.stopped
                expect_stop(lambda:society.get(url+'/next'));assert opener.call_count==1
            assertions+=1
            practice.configure(root/'practice');practice.robot=allow_robots();url='https://www.zyshgzb.gov.cn/n1/example'
            with patch.object(practice,'open_public',return_value=Response(body,url)) as opener,patch.object(practice.time,'sleep'):
                expect_stop(lambda:practice.fetch(url));assert practice.stopped
                expect_stop(lambda:practice.fetch(url+'/next'));assert opener.call_count==1
            assertions+=1
            harvester=journals.Harvester(root/'journals');host='shjs.ruc.edu.cn';harvester.robots[host]=allow_robots();url='https://'+host+'/CN/example'
            with patch.object(journals,'open_public',return_value=Response(body,url)) as opener,patch.object(journals.time,'sleep'):
                expect_stop(lambda:harvester.request(url));assert host in harvester.stopped
                expect_stop(lambda:harvester.request(url+'/next'));assert opener.call_count==1
            assertions+=1
    assert_no_access_challenge('<html><title>社会建设</title><body>研究摘要：本研究采用访谈方法研究社区参与。</body></html>'.encode())
    print(json.dumps({'passed':True,'network_requests':0,'mock_cases':assertions,'challenge_payloads':len(payloads),'crawlers_tested':3,'first_challenge_requests_per_host':1,'subsequent_requests_after_stop':0,'normal_article_control':'passed','validation_scope':'HTTP 200 challenge detected before article parsing, no retries, host remains stopped'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
