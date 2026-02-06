#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NICE 신용평가 테스트 스크립트
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

from scrapers_group3.nice import NICEScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def test_nice_scraper():
    """NICE 스크래퍼 테스트"""
    
    # 테스트 기간 설정 (1개월)
    start_date = "2026-01-01"
    end_date = "2026-01-31"
    
    print(f"\n{'='*80}")
    print(f"🔍 NICE 신용평가 테스트")
    print(f"📅 기간: {start_date} ~ {end_date}")
    print(f"{'='*80}\n")
    
    scraper = NICEScraper(start_date, end_date)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ko-KR',
            timezone_id='Asia/Seoul'
        )
        
        page = await scraper._setup_page(context)
        
        try:
            collected = await scraper.scrape(page)
            
            print(f"\n{'='*80}")
            print(f"✅ 수집 완료: {collected}건")
            print(f"{'='*80}\n")
            
            # 결과 출력
            # 결과 출력 및 다운로드 검증
            if scraper.results:
                print("📊 수집 결과 및 다운로드 검증:\n")
                
                # 검증을 위한 헤더 설정
                headers = {
                    "Referer": "https://www.nicerating.com/research/researchAll.do",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                for i, item in enumerate(scraper.results[:10], 1):
                    print(f"{i}. {item['title'][:50]}")
                    print(f"   날짜: {item['date']}")
                    pdf_url = item.get('pdf_url', 'N/A')
                    print(f"   PDF URL: {pdf_url[:80]}...")
                    
                    if pdf_url != 'N/A' and pdf_url.startswith('http'):
                        try:
                            # HEAD 요청으로 파일 존재 여부 확인 (APIRequestContext 사용)
                            response = await context.request.get(pdf_url, headers=headers)
                            status = response.status
                            content_type = response.headers.get('content-type', '')
                            content_disp = response.headers.get('content-disposition', '')
                            
                            if status == 200:
                                print(f"   ✅ [검증 성공] 다운로드 가능 (Status: 200)")
                                print(f"      Content-Type: {content_type}")
                            else:
                                print(f"   ❌ [검증 실패] Status: {status}, Type: {content_type}")
                            
                            # 응답 닫기 (메모리 해제)
                            await response.dispose()
                                
                        except Exception as e:
                            print(f"   ⚠️ [검증 에러] {e}")
                    print("")
                
                # CSV 저장
                output_dir = r"D:\Antigravity\coding\output"
                os.makedirs(output_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"nice_{timestamp}.csv"
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
    asyncio.run(test_nice_scraper())
