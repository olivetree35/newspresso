"""
KDI 정책자료실 PDF URL 수집기 (국토개발 분야)
- URL: https://eiec.kdi.re.kr/policy/materialList.do?depth1=A0000&depth2=A0600

사용 방법:
    python 04_kdi_scraper.py --start 2026-01-01 --end 2026-01-31
"""

import argparse
import json
import csv
import sys
import os
import re
from datetime import datetime
from typing import List, Dict
import requests
import certifi
from bs4 import BeautifulSoup


LIST_URL = "https://eiec.kdi.re.kr/policy/materialList.do"
SITE_NAME = "KDI"
TARGET_SUBJECT = "국토개발"
DEBUG_DUMP_LIMIT = 3


def parse_date(date_str: str):
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except:
            pass
    return None


def _first_text(elem):
    return elem.get_text(strip=True) if elem else ""


def _extract_field(soup: BeautifulSoup, labels):
    for label in labels:
        th = soup.find(lambda tag: tag.name in ("th", "dt", "label", "span") and tag.get_text(strip=True) == label)
        if th:
            if th.name == "dt":
                dd = th.find_next_sibling("dd")
                return _first_text(dd)
            if th.name in ("th", "label", "span"):
                td = th.find_next_sibling("td")
                if td:
                    return _first_text(td)
                parent = th.parent
                if parent:
                    next_td = parent.find("td")
                    if next_td and next_td is not th:
                        return _first_text(next_td)
    return ""


def _extract_download_url(soup: BeautifulSoup):
    # 1) 직접 링크 (pdf 또는 파일다운로드 엔드포인트)
    for a in soup.select('a[href]'):
        href = a.get('href', '')
        if not href:
            continue
        if href.lower().endswith('.pdf') or 'fileDown' in href or 'filedown' in href or 'download' in href:
            if href.startswith('http'):
                return href
            return f"https://eiec.kdi.re.kr{href if href.startswith('/') else '/' + href}"

    # 2) download 버튼의 data-* 속성에서 링크 추정
    btn = soup.select_one('button.download[onclick*="fileBubble"]')
    if btn:
        for attr, val in btn.attrs.items():
            if isinstance(val, str):
                if val.lower().endswith('.pdf') or '/download' in val or 'fileDown' in val:
                    if val.startswith('http'):
                        return val
                    return f"https://eiec.kdi.re.kr{val if val.startswith('/') else '/' + val}"

    # 3) 스크립트 내 URL 패턴 탐색
    scripts = soup.find_all('script')
    for s in scripts:
        text = s.get_text(" ", strip=True)
        if not text:
            continue
        m = re.search(r'(https?://[^\s\'"]+\.pdf)', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'(/[^\s\'"]+\.pdf)', text, re.I)
        if m:
            return f"https://eiec.kdi.re.kr{m.group(1)}"

    return ""


def scrape(start_date: str, end_date: str, limit: int = None):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9'
    })
    session.verify = False
    
    results = []
    debug_dump_count = 0
    
    print("=" * 80)
    print(f"{SITE_NAME} PDF URL 수집")
    print(f"수집 기간: {start_date} ~ {end_date}")
    print(f"수집 분야: {TARGET_SUBJECT}")
    print("=" * 80)
    
    page = 1
    max_pages = 5
    
    while page <= max_pages:
        if limit and len(results) >= limit:
            break
        
        url = f"{LIST_URL}?depth1=A0000&depth2=A0600&page={page}"
        print(f"\n📄 페이지 {page} 요청...")
        
        try:
            response = session.get(url, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"❌ 페이지 로드 실패: {e}")
            break
        
        # 게시물 목록 찾기
        items = soup.select('li a[href*="materialView"], tr td a[href*="materialView"], .list a[href*="view"]')
        
        if not items:
            print(f"⚠️ 게시물 없음 - 종료")
            break
        
        print(f"   {len(items)}개 게시물 발견")
        
        for item in items:
            if limit and len(results) >= limit:
                break
            
            title = item.get_text(strip=True)
            href = item.get('href', '')
            
            if not title or len(title) < 5:
                continue
            
            # 날짜 추출 (부모 요소에서)
            parent = item.find_parent('tr') or item.find_parent('li') or item.find_parent('div')
            date_str = ""
            
            if parent:
                date_elem = parent.find(['span', 'td', 'li'], class_=re.search(r'date|time|day', str(parent), re.I))
                if date_elem:
                    date_str = date_elem.get_text(strip=True)
                else:
                    # 모든 텍스트에서 날짜 검색
                    text = parent.get_text(strip=True)
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                    if date_match:
                        date_str = date_match.group(1)
            
            if not date_str:
                date_str = ""
            
            pub_date = parse_date(date_str)
            if not pub_date:
                pub_date = None
            
            if pub_date and not (start_dt <= pub_date <= end_dt):
                continue
            
            if 'materialView' in href:
                if href.startswith('?'):
                    detail_url = f"https://eiec.kdi.re.kr{href}"
                elif not href.startswith('http'):
                    detail_url = f"https://eiec.kdi.re.kr/{href}"
                else:
                    detail_url = href
            else:
                continue

            # 상세 페이지에서 분야/발간처/다운로드 URL 추출
            try:
                detail_res = session.get(detail_url, timeout=15)
                detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
            except Exception as e:
                print(f"   ⚠️ 상세페이지 로드 실패: {e}")
                continue

            if debug_dump_count < DEBUG_DUMP_LIMIT:
                os.makedirs("output", exist_ok=True)
                debug_path = os.path.join("output", f"kdi_detail_dump_p{page}_i{debug_dump_count+1}.html")
                try:
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(detail_res.text)
                    print(f"   🧪 상세 HTML 덤프: {debug_path}")
                except Exception as e:
                    print(f"   ⚠️ 덤프 저장 실패: {e}")
                debug_dump_count += 1

            subject = _extract_field(detail_soup, ["주제", "분야", "정책분야", "정책 분야"])
            if not subject:
                # 목록에서라도 확인
                parent_text = parent.get_text(" ", strip=True) if parent else ""
                subject = TARGET_SUBJECT if TARGET_SUBJECT in parent_text else ""

            if TARGET_SUBJECT not in subject:
                continue

            if not pub_date:
                date_fallback = _extract_field(detail_soup, ["발간일", "발행일", "등록일", "게시일"])
                pub_date = parse_date(date_fallback)
                if pub_date:
                    date_str = date_fallback

            if pub_date and not (start_dt <= pub_date <= end_dt):
                continue

            publisher = _extract_field(detail_soup, ["발간처", "발행처", "발간기관", "발행기관", "출처"])
            download_url = _extract_download_url(detail_soup)
            if not download_url:
                print(f"   ⚠️ 다운로드 URL 없음: {title[:40]}...")
                continue
            
            results.append({
                'title': title,
                'date': date_str,
                'publisher': publisher,
                'site_name': SITE_NAME,
                'download_url': download_url,
                'subject': subject
            })
            print(f"   ✅ {title[:40]}... ({date_str})")
        
        page += 1
    
    return results


def save_results(results, output_dir="output"):
    if not results:
        return
    
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    with open(f"{output_dir}/kdi_{ts}.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON: {output_dir}/kdi_{ts}.json")
    
    with open(f"{output_dir}/kdi_{ts}.csv", 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['No.', 'Date', 'Site Name', 'Title', 'Publisher', 'Download URL', 'Subject'])
        for i, r in enumerate(results, 1):
            w.writerow([i, r.get('date', ''), r['site_name'], r['title'], r.get('publisher', ''), r['download_url'], r.get('subject', '')])
    print(f"💾 CSV: {output_dir}/kdi_{ts}.csv")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass
    p = argparse.ArgumentParser(description=f'{SITE_NAME} PDF 수집')
    p.add_argument('--start', help='시작 (YYYY-MM-DD)')
    p.add_argument('--end', help='종료 (YYYY-MM-DD)')
    p.add_argument('--limit', type=int)
    p.add_argument('--output-dir', default='output')
    args = p.parse_args()
    
    if args.start and args.end:
        s, e = args.start, args.end
    else:
        print("📅 날짜 (YYYY-MM-DD)")
        s, e = input("시작: ").strip(), input("종료: ").strip()
    
    try:
        datetime.strptime(s, "%Y-%m-%d")
        datetime.strptime(e, "%Y-%m-%d")
    except:
        print("❌ 날짜 형식 오류")
        sys.exit(1)
    
    r = scrape(s, e, args.limit)
    
    print("\n" + "=" * 80)
    print(f"수집 결과: {len(r)}개")
    print("=" * 80)
    
    for i, item in enumerate(r, 1):
        print(f"{i}. {item.get('date', '')} | {item['title'][:40]}...")
    
    save_results(r, args.output_dir)
    
    if r:
        print(f"\n✅ 완료! {len(r)}개")
    else:
        print("\n⚠️ 데이터 없음")


if __name__ == "__main__":
    main()



