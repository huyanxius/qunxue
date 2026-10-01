#!/usr/bin/env python3
"""Optional local OCR of actually advertised contents images; review queue only.
Requires installed tesseract (chi_sim) and Pillow. Image bytes stay in memory.
"""
import argparse
import io
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from history import Fetcher, ROOT, dump, image_metadata, parse_tsv, toc_candidates, now


def parse_image(body):
    meta = image_metadata(body)
    image = Image.open(io.BytesIO(body)).convert('RGB')
    image = image.resize((image.width * 3, image.height * 3))
    encoded = io.BytesIO()
    image.save(encoded, format='PNG')
    response = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'chi_sim', '--psm', '3', 'tsv'],
                              input=encoded.getvalue(), capture_output=True, timeout=45, check=True)
    lines = parse_tsv(response.stdout.decode('utf-8'), image.width, image.height)
    # Only contents-column OCR metadata leaves memory; no original image or article body.
    meta['review_lines'] = [r for r in lines if r['x'] > 0.42]
    label = ' '.join(r['text'] for r in lines)
    import re
    match = re.search(r'(20\d{2})年第?(\d{1,2})期', re.sub(r'\s+', '', label))
    if match:
        meta.update(publication_year=int(match[1]), publication_issue=int(match[2]))
    meta.update(published_at=None, published_at_precision='issue' if match else 'unknown',
                verification_status='review_queue', ocr_engine='tesseract chi_sim 3x psm3',
                date_basis='explicit_toc_issue_label_ocr_pending_review' if match else 'no_publication_label_detected')
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True, help='history.py image-group records.json')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--allow-network', action='store_true')
    ap.add_argument('--max-images', type=int, default=4)
    args = ap.parse_args()
    if not args.allow_network: ap.error('Requires --allow-network')
    if not shutil.which('tesseract'): ap.error('Install an authorized local OCR runtime first')
    if not 1 <= args.max_images <= 40: ap.error('--max-images must be 1..40')
    out = args.output.resolve()
    if ROOT.parents[1] in out.parents and ROOT not in out.parents: ap.error('Refusing existing repository path')
    import fcntl, tempfile
    lock = open(Path(tempfile.gettempdir()) / 'qunxue-frontier-www.cycrc.org.cn.lock', 'a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: ap.error('Another collector owns publisher host')
    groups = json.loads(args.input.read_text())
    urls = list(dict.fromkeys(u for group in groups for u in group.get('image_urls', [])))
    fetcher = Fetcher(out, hosts={'www.cycrc.org.cn'})
    images, errors = [], []
    for url in urls[:args.max_images]:
        try:
            row = fetcher.read(url, parse_image)
            images.append(dict(row, url=url))
            dump(out / 'image-metadata.json', images)
            print(f'Captured {len(images)}/{min(len(urls),args.max_images)} directory images', flush=True)
        except Exception as e:
            errors.append({'url':url, 'reason':str(e)})
            break
    issues = sorted({(r['publication_year'],r['publication_issue']) for r in images if r.get('publication_issue')})
    report={'captured_at':now(), 'advertised_image_count':len(urls), 'fetched_image_count':len(images),
            'missing_advertised_image_count':len(urls)-len(images), 'ocr_labeled_issues':issues,
            'article_expected_count':None,'article_fetched_count':0,'article_missing_count':None,
            'historical_coverage_complete':False,'errors':errors,'full_text_verified':False,
            'scope':'directory image hashes and unverified OCR lines; no research findings or summaries',
            'input_sha256':__import__('hashlib').sha256(args.input.read_bytes()).hexdigest()}
    dump(out / 'ocr-coverage.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return bool(errors)

if __name__ == '__main__': raise SystemExit(main())
