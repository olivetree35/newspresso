#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Group 3 통합 수집기 (Main Operator)
- CLI 인자 지원 (--site, --start, --end)
- 미입력 시 Interactive 모드 지원
"""

import sys
import os
import asyncio
import logging
import argparse
import csv
from datetime import datetime

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 내부 모듈 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from playwright.async_api import async_playwright
# 개별 스크래퍼 import
from scrapers_group3.lh_ri import LHScraper
from scrapers_group3.kif import KIFScraper
from scrapers_group3.nice import NICEScraper
from scrapers_group3.kdi import KDIScraper
from scrapers_group3.utils import save_to_csv

# 스크래퍼 등록 맵
SCRAPERS = {
    'lh': LHScraper,
    'kif': KIFScraper,
    'nice': NICEScraper,
    'kdi': KDIScraper,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Main")

async def run_scraper(site_code: str, start_date: str, end_date: str):
    print(f"\n🚀 스크래퍼 실행: {site_code.upper()} ({start_date} ~ {end_date})")
    
    if site_code not in SCRAPERS:
        print(f"❌ 지원하지 않는 사이트 코드입니다: {site_code}")
        print(f"   지원 목록: {list(SCRAPERS.keys())}")
        return

    scraper_cls = SCRAPERS[site_code]
    
    async with async_playwright() as p:
        # 브라우저 런칭
        browser = await p.chromium.launch(headless=True)
        # 중요: User-Agent 설정
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        # 스크래퍼 초기화 및 실행
        # 각 스크래퍼는 (start_date, end_date)를 인자로 받음
        scraper = scraper_cls(start_date, end_date)
        
        # 페이지 생성 (네트워크 리스너 등록 등 포함될 수 있음)
        # BaseScraper의 _on_response를 쓰려면 page 생성 시 hook 필요
        # 하지만 현재 구현은 scraper.scrape(page) 내부 로직에 의존하거나
        # scraper._setup_page()를 호출해야 함.
        pass
        
        # AsyncBaseScraper 구조상 _setup_page가 있으므로 활용
        page = await scraper._setup_page(context)
        
        count = await scraper.scrape(page)
        
        await context.close()
        await browser.close()
        
        print(f"✅ 수집 완료: 총 {count}건")
        
        # 결과 저장 (CSV)
        save_to_csv(scraper.results, site_code)
        
        # 결과 출력 (검증용)
        if scraper.results:
            print("\n🔍 [수집 데이터 샘플]")
            for item in scraper.results[:5]:
                print(f" - {item['date']} | {item['title'][:30]}... | PDF: {item['pdf_url']}")
                if item['pdf_url'] == 'N/A' or not item['pdf_url']:
                    print(f"   ⚠️ PDF URL 누락 확인 필요: {item['page_url']}")

def main():
    parser = argparse.ArgumentParser(description='Group 3 Scraper Executor')
    parser.add_argument('--site', help='사이트 코드 (lh, kif, ...)')
    parser.add_argument('--start', help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--end', help='종료일 (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # 인자가 없으면 인터랙티브 모드 (여기선 생략하고 CLI 위주로 구현)
    if not args.site or not args.start or not args.end:
        print("❌ 사용법: python main_group3.py --site [code] --start [YYYY-MM-DD] --end [YYYY-MM-DD]")
        # 필요 시 input() 로직 추가 가능
        return

    asyncio.run(run_scraper(args.site, args.start, args.end))

if __name__ == "__main__":
    main()
