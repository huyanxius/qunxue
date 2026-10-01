"""Bounded offline behavior tests; fixtures use synthetic text, no source bodies."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    import history
except ImportError:
    history = None


class HistoryTests(unittest.TestCase):
    def api(self, name):
        fn = getattr(history, name, None)
        self.assertTrue(callable(fn), f"Missing required behavior: {name}")
        return fn

    def test_month_date_is_not_promoted_to_day(self):
        fn = self.api('publication_date')
        self.assertEqual(fn('2025年3月'), ('2025-03', 'month'))
        self.assertEqual(fn('2025年第3期'), (None, 'issue'))
        self.assertEqual(fn('2025年2月30日'), (None, 'unknown'))
        self.assertEqual(fn('2025年03月12日'), ('2025-03-12', 'day'))

    def test_challenge_variants_stop_including_http_200_token_and_javascript(self):
        fn = self.api('check_access')
        for body in [b'<h1>Please enable JavaScript and refresh the page.</h1>',
                     '{"success":false,"message":"TOKEN无效，请重新登录"}'.encode(),
                     b'<title>captcha</title>']:
            with self.assertRaises(RuntimeError):
                fn(body)
        fn('<title>期刊目录</title><p>本文研究数字技术</p>'.encode())

    def test_discovery_uses_actual_archive_links_and_excludes_other_hosts_and_years(self):
        fn = self.api('journal_issues')
        page = b'<a href="/Magazine/?Year=2025&amp;Issue=2">I2</a><a href="/Magazine/?Year=2024&amp;Issue=1">old</a><a href="https://evil.test/Magazine/?Year=2025&amp;Issue=1">x</a><a href="/Magazine/?Year=2025&amp;Issue=2">dup</a>'
        rows = fn(page, 'https://shxyj.ajcass.com/', '2025-01-01', '2026-10-02')
        self.assertEqual(rows, [{'url': 'https://shxyj.ajcass.com/Magazine/?Year=2025&Issue=2', 'publication_year': 2025, 'publication_issue': 2}])

    def test_unknown_denominator_and_bounded_pages_never_claim_complete(self):
        fn = self.api('coverage')
        row = fn('example', 4, 2, expected=None, enumeration_complete=False)
        self.assertIsNone(row['expected_count'])
        self.assertIsNone(row['missing_count'])
        self.assertEqual(row['discovered_unfetched_count'], 2)
        self.assertFalse(row['coverage_complete'])
        self.assertFalse(fn('example', 4, 4, expected=4, enumeration_complete=False)['coverage_complete'])

    def test_newspaper_calendar_preserves_issue_dates_deduplicates_and_filters_window(self):
        fn = self.api('newspaper_calendar')
        payload = {'a': ['<a href="/issue/a">1月2日</a>', '<a href="/issue/a">1月2日</a>', '<a href="/issue/b">12月31日</a>']}
        self.assertEqual(fn(json.dumps(payload).encode(), 'https://www.zyshgzb.gov.cn/', 2026, '2025-01-01', '2026-10-02'), [{'url': 'https://www.zyshgzb.gov.cn/issue/a', 'published_at': '2026-01-02'}])

    def test_dedup_quarantines_all_abstract_collisions_without_missing_author_merges(self):
        fn = self.api('deduplicate')
        rows = [{'id':'a','title':'甲','authors':[],'url':'https://x/a','abstract_sha256':'same'},
                {'id':'b','title':'乙','authors':[],'url':'https://x/b','abstract_sha256':'same'},
                {'id':'c','title':'丙','authors':[],'url':'https://x/c'},
                {'id':'d','title':'丙','authors':[],'url':'https://x/d'}]
        keep, quarantine = fn(rows)
        self.assertEqual([r['id'] for r in keep], ['c','d'])
        self.assertEqual({r['id'] for r in quarantine}, {'a','b'})

    def test_fetch_cache_resumes_parsed_metadata_without_storing_body(self):
        cls = self.api('Fetcher')
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = cls(Path(tmp), hosts={'www.cycrc.org.cn'}, min_interval=0)
            body = b'<html><title>public</title></html>'
            calls=[]
            def transport(url):
                calls.append(url)
                return 200, {'Content-Type':'text/html','X-Robots-Tag':'noarchive'}, body
            fetcher.transport = transport
            url='https://www.cycrc.org.cn/robots.txt'
            fetcher.read(url, lambda b: {'parsed':True}, robots_probe=True)
            second=cls(Path(tmp),hosts={'www.cycrc.org.cn'},min_interval=0)
            second.transport=lambda u: self.fail('resume opened network')
            self.assertEqual(second.read(url, lambda b: {})['parsed'],True)
            self.assertEqual(len(calls),1)
            self.assertNotIn(body.decode(), '\n'.join(p.read_text() for p in Path(tmp).rglob('*') if p.is_file()))

    def test_access_stop_persists_across_resume_before_next_request(self):
        cls = self.api('Fetcher')
        with tempfile.TemporaryDirectory() as tmp:
            f=cls(Path(tmp),hosts={'www.cycrc.org.cn'},min_interval=0)
            f.transport=lambda u: (403,{},b'denied')
            with self.assertRaises(RuntimeError): f.read('https://www.cycrc.org.cn/robots.txt',lambda b: {},robots_probe=True)
            resumed=cls(Path(tmp),hosts={'www.cycrc.org.cn'},min_interval=0)
            resumed.transport=lambda u: self.fail('stopped host requested again')
            with self.assertRaises(RuntimeError): resumed.read('https://www.cycrc.org.cn/',lambda b: {},robots_probe=True)

    def test_publisher_archive_follows_only_actual_journal_entries(self):
        fn=self.api('publisher_links')
        body='<a href="/xsqk/qnyj/qnyj2025/">2025</a><a href="/xsqk/qnyj/qnyj2024/">2024</a><a href="/xsqk/qnyj/qnyj2025/202501/t20250101_1.html">2025年第1期</a><a href="/kycg/qnyj/">other</a>'
        rows=fn(body.encode(),'https://www.cycrc.org.cn/xsqk/qnyj/zdqs_qn/','2025-01-01','2026-10-02')
        self.assertEqual(len(rows['archives']),1)
        self.assertEqual(rows['issues'][0]['publication_issue'],1)
        self.assertEqual(rows['issues'][0]['published_at_precision'],'issue')
        self.assertIsNone(rows['issues'][0]['published_at'])

    def test_publisher_issue_marks_upload_date_separately_from_issue_publication(self):
        fn=self.api('publisher_issue')
        body='<h1>2025年第1期</h1><div class="TRS_Editor"><p>人工智能与青年发展</p><p>张甲；李乙</p><p>摘要：这是合成测试材料。</p></div><meta name="PubDate" content="2025-02-05">'
        row=fn(body.encode(),'https://www.cycrc.org.cn/xsqk/qnyj/qnyj2025/202502/t20250205_1.html')
        self.assertEqual(row['publication_year'],2025)
        self.assertEqual(row['publication_issue'],1)
        self.assertIsNone(row['published_at'])
        self.assertEqual(row['published_at_precision'],'issue')
        self.assertEqual(row['page_uploaded_at'],'2025-02-05')
        self.assertNotIn('body',row)

    def test_image_archive_counts_groups_without_guessing_issue_from_folder_or_filename(self):
        fn=self.api('publisher_images')
        body='<div class="bookdesc"><img src="/xsqk/qnyj/qnyj2025/202601/A.png"><img src="/xsqk/qnyj/qnyj2025/202601/B.png"></div><div class="bookdesc"><img src="/xsqk/qnyj/qnyj2025/202512/C.png"></div>'
        groups=fn(body.encode(),'https://www.cycrc.org.cn/xsqk/qnyj/qnyj2025/')
        self.assertEqual(len(groups),2)
        self.assertEqual(len(groups[0]['image_urls']),2)
        self.assertIsNone(groups[0]['publication_issue'])
        self.assertEqual(groups[0]['published_at_precision'],'unknown')

    def test_binary_image_probe_never_claims_article_text(self):
        fn=self.api('image_metadata')
        import struct
        body=b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+struct.pack('>II',640,900)+b'x'*20
        row=fn(body)
        self.assertEqual(row['width'],640)
        self.assertEqual(row['height'],900)
        self.assertEqual(row['content_scope'],'directory_image')
        self.assertFalse(row['full_text_verified'])
        with self.assertRaises(ValueError):fn(b'<html>empty</html>')

    def test_issue_ocr_title_is_not_calendar_date_and_keeps_evidence_locator(self):
        fn=self.api('toc_candidates')
        lines=[{'text':'2025年第12期 总第358期（月刊）','confidence':0.99,'x':0.05,'y':0.9},
               {'text':'人工智能与青年社会','confidence':0.95,'x':0.5,'y':0.8},
               {'text':'张甲 李乙/5','confidence':0.98,'x':0.7,'y':0.7}]
        rows=fn(lines,'https://www.cycrc.org.cn/xsqk/qnyj/qnyj2025/202601/A.png')
        self.assertEqual(rows['publication_year'],2025)
        self.assertEqual(rows['publication_issue'],12)
        self.assertEqual(rows['published_at_precision'],'issue')
        self.assertIsNone(rows['published_at'])
        self.assertFalse(rows['full_text_verified'])
        self.assertNotIn('findings',rows)

    def test_tesseract_tsv_merges_words_into_lines_with_observable_confidence(self):
        fn=self.api('parse_tsv')
        tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t300\t100\t100\t20\t95\t青年\n5\t1\t1\t1\t1\t2\t410\t100\t100\t20\t85\t研究\n'
        rows=fn(tsv,600,900)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['text'],'青年 研究')
        self.assertEqual(rows[0]['confidence'],0.85)
        self.assertEqual(rows[0]['x'],0.5)

    def test_jpeg_directory_image_with_png_suffix_is_identified_by_bytes(self):
        fn=self.api('image_metadata')
        from PIL import Image
        import io
        buffer=io.BytesIO();Image.new('RGB',(400,800)).save(buffer,format='JPEG')
        row=fn(buffer.getvalue())
        self.assertEqual(row['width'],400)
        self.assertEqual(row['height'],800)
        self.assertEqual(row['format'],'JPEG')
        self.assertFalse(row['full_text_verified'])

    def test_tsv_literal_quote_does_not_swallow_following_lines(self):
        fn=self.api('parse_tsv')
        header='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
        tsv=header+'5\t1\t1\t1\t1\t1\t10\t10\t10\t10\t90\t"\n'+'5\t1\t1\t1\t2\t1\t10\t30\t10\t10\t90\t青年\n'
        rows=fn(tsv,100,100)
        self.assertEqual([r['text'] for r in rows],['"','青年'])

    def test_cli_requires_network_opt_in_before_any_source_work(self):
        import subprocess
        result=subprocess.run([sys.executable,str(ROOT/'history.py'),'--output','/tmp/never-used-history'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('allow-network',result.stderr)

    def test_unapproved_credentials_redirect_and_host_are_rejected(self):
        fn=self.api('validate_url')
        for url in ['http://www.cycrc.org.cn/', 'https://user:pw@www.cycrc.org.cn/', 'https://www.cycrc.org.cn:444/', 'https://127.0.0.1/']:
            with self.assertRaises(ValueError): fn(url, {'www.cycrc.org.cn'})

    def test_mixed_publisher_feed_preserves_pdf_links_without_claiming_journal_identity(self):
        spec=importlib.util.spec_from_file_location('publisher_feed',ROOT/'china-youth-review-20261002'/'collect_publisher_feed.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        body='<a href="202503/P.pdf">其他刊物论文2025-03-20</a><a href="https://mp.weixin.qq.com/s/example">青年 生活2026-06-01</a><a href="https://evil.invalid/a">忽略2026-01-01</a>'.encode()
        result=module.parse_feed(body,'https://www.cycrc.org.cn/kycg/qnyj/')
        self.assertEqual(len(result['links']),2)
        self.assertEqual(result['links'][1]['title'],'青年 生活')
        for row in result['links']:
            self.assertFalse(row['journal_identity_verified'])
            self.assertIsNone(row['published_at'])
            self.assertFalse(row['display_ready'])


if __name__ == '__main__': unittest.main()
