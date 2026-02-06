"""
한국금융연구원(KIF) PDF URL 수집기 - Selenium 버전
사용법: python 02_kif_scraper.py 2025-01-01 2026-01-31
"""

import json
import csv
import sys
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class KIFScraper:
    BASE_URL = "https://www.kif.re.kr"
    LIST_URL = "https://www.kif.re.kr/kif4/publication/pub_list"
    SITE_NAME = "한국금융연구원"
    
    def __init__(self, start_date: str, end_date: str, mid: int = 10, limit: Optional[int] = None, output_dir: str = "output"):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.mid = mid
        self.limit = limit
        self.output_dir = output_dir
        self.driver = None
        self.results: List[Dict] = []
        os.makedirs(output_dir, exist_ok=True)
    
    def _init_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        self.driver = webdriver.Chrome(options=options)
    
    def _close_driver(self):
        if self.driver:
            self.driver.quit()
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str or '')
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d")
            except:
                pass
        return None
    
    def _is_in_date_range(self, pub_date: datetime) -> bool:
        return self.start_date <= pub_date <= self.end_date
    
    def _extract_download_url(self) -> Optional[str]:
        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, 'button[onclick*="execDownload"]')
            onclick = btn.get_attribute('onclick')
            
            match = re.search(r"execDownload\([^,]*,\s*(\d+),\s*(\d+),\s*(\d+),\s*'([^']+)'", onclick)
            if match:
                mid, vid, cno, fcd = match.groups()
                return f"{self.BASE_URL}/kif4/publication/viewer?mid={mid}&vid={vid}&cno={cno}&fcd={fcd}&ft=0"
        except:
            pass
        return None
    
    def _get_list_items(self) -> List[Dict]:
        items = []
        url = f"{self.LIST_URL}?mid={self.mid}"
        
        self.driver.get(url)
        sleep(2)
        
        links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="pub_detail"]')
        
        for link in links:
            try:
                href = link.get_attribute('href')
                if not href:
                    continue
                
                title_elem = link.find_elements(By.CSS_SELECTOR, '.title')
                title = title_elem[0].text.strip() if title_elem else link.text.strip()
                
                if not title or len(title) < 3:
                    continue
                
                cno_match = re.search(r'cno=(\d+)', href)
                cno = cno_match.group(1) if cno_match else ''
                
                items.append({
                    'title': title,
                    'detail_url': href,
                    'cno': cno
                })
            except:
                continue
        
        return items
    
    def scrape(self) -> List[Dict]:
        print("=" * 70)
        print(f"{self.SITE_NAME} PDF URL 수집기 (mid={self.mid})")
        print("=" * 70)
        print(f"수집 기간: {self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')}")
        if self.limit:
            print(f"수집 제한: {self.limit}개")
        print("-" * 70)
        
        self._init_driver()
        
        try:
            items = self._get_list_items()
            print(f"\n📄 {len(items)}개 게시물 발견\n")
            
            for idx, item in enumerate(items, 1):
                if self.limit and len(self.results) >= self.limit:
                    print(f"\n✅ 수집 개수 제한({self.limit}개)에 도달")
                    break
                
                print(f"[{idx}/{len(items)}] {item['title'][:45]}...")
                
                self.driver.get(item['detail_url'])
                sleep(2)
                
                download_url = self._extract_download_url()
                
                if download_url:
                    fcd_match = re.search(r'fcd=([^&]+)', download_url)
                    fcd = fcd_match.group(1) if fcd_match else ''
                    
                    self.results.append({
                        'title': item['title'],
                        'date': '',
                        'site_name': self.SITE_NAME,
                        'download_url': download_url,
                        'cno': item['cno'],
                        'fcd': fcd
                    })
                    print(f"   ✅ {download_url}")
                else:
                    print(f"   ⚠️ PDF URL 없음")
        
        finally:
            self._close_driver()
        
        return self.results
    
    def print_results(self):
        print("\n" + "=" * 70)
        print("수집 결과")
        print("=" * 70)
        
        if not self.results:
            print("수집된 데이터가 없습니다.")
            return
        
        print(f"총 {len(self.results)}개\n")
        for idx, item in enumerate(self.results, 1):
            print(f"[{idx}] {item['title'][:40]}")
            print(f"    → {item['download_url']}")
        print("-" * 70)
    
    def save_to_json(self) -> str:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(self.output_dir, f"kif_{ts}.json")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'site': self.SITE_NAME,
                'count': len(self.results),
                'data': self.results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 JSON: {filepath}")
        return filepath
    
    def save_to_csv(self) -> str:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(self.output_dir, f"kif_{ts}.csv")
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['No.', 'Title', 'Download URL', 'cno', 'fcd'])
            for i, r in enumerate(self.results, 1):
                w.writerow([i, r['title'], r['download_url'], r['cno'], r.get('fcd', '')])
        
        print(f"💾 CSV: {filepath}")
        return filepath


def main():
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass
        
    start_date = None
    end_date = None
    
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        print("\n" + "="*50)
        print("한국금융연구원 스크래퍼 (Selenium)")
        print("="*50)
        try:
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            start_date = start_in if start_in else "2024-01-01"
            end_in = input("종료일 (YYYY-MM-DD) [기본: 오늘]: ").strip()
            end_date = end_in if end_in else datetime.now().strftime("%Y-%m-%d")
        except KeyboardInterrupt:
            sys.exit(0)
    
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except:
        print(f"❌ 날짜 형식 오류: {start_date}, {end_date}")
        sys.exit(1)
    
    scraper = KIFScraper(start_date, end_date)
    scraper.scrape()
    scraper.print_results()
    
    if scraper.results:
        scraper.save_to_json()
        scraper.save_to_csv()
        print(f"\n✅ 완료! {len(scraper.results)}개 수집")
    else:
        print("\n⚠️ 수집된 데이터 없음")


if __name__ == "__main__":
    main()

# 수정: 2026-01-30 20:05 - Selenium 사용 (JS 렌더링 필요)
