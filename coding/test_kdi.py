#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDI 테스트 스크립트
"""

import asyncio
import sys
import os
import logging
import csv
from datetime import datetime
from playwright.async_api import async_playwright

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers_group3.kdi import KDIScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def test_kdi_scraper():
    """KDI 스크래퍼 테스트"""
    
    # 테스트 기간 설정 (1개월 단위 테스트)
    start_date = "2026-01-01"
    end_date = "2026-01-31"
    
    print(f"\n{'='*80}")
    print(f"🔍 KDI 정책자료실 테스트")
    print(f"📅 기간: {start_date} ~ {end_date}")
    print(f"{'='*80}\n")
    
    scraper = KDIScraper(start_date, end_date)
    
    async with async_playwright() as p:
        # 봇 감지 우회 설정 포함
        browser = await p.chromium.launch(
            headless=False,  # True로 변경하면 백그라운드 실행
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ko-KR',
            timezone_id='Asia/Seoul',
            extra_http_headers={
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        )
        
        # 자동화 감지 방지
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
        """)
        
        page = await scraper._setup_page(context)
        
        try:
            collected = await scraper.scrape(page)
            
            print(f"\n{'='*80}")
            print(f"✅ 수집 완료: {collected}건")
            print(f"{'='*80}\n")
            
            # 결과 출력
            if scraper.results:
                print("📊 수집 결과:\n")
                for i, item in enumerate(scraper.results[:10], 1):
                    print(f"{i}. {item['title'][:50]}")
                    print(f"   날짜: {item['date']}")
                    print(f"   PDF: {item['pdf_url'][:80] if item['pdf_url'] != 'N/A' else '(미추출)'}\n")
                
                # CSV 저장
                output_dir = r"D:\Antigravity\coding\output"
                os.makedirs(output_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"kdi_{timestamp}.csv"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=['source', 'title', 'date', 'page_url', 'pdf_url', 'collected_at'])
                    writer.writeheader()
                    writer.writerows(scraper.results)
                
                print(f"💾 결과 저장: {filepath}")
            else:
                print("⚠️ 수집된 데이터가 없습니다.")
        
        except Exception as e:
            logger.error(f"테스트 실패: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_kdi_scraper())
