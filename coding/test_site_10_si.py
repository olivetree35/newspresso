#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서울연구원 스크래퍼 테스트 (직접 다운로드 확인)
"""

import asyncio
import sys
import os
import logging
from datetime import datetime

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

import importlib

# 동적 임포트 (숫자로 시작하는 모듈명 대응)
# from scrapers_group3.10_si_scraper import SIScraper (SyntaxError)
try:
    module = importlib.import_module("scrapers_group3.10_si_scraper")
except ImportError:
    # 경로 추가 후 재시도
    sys.path.append(os.path.join(os.path.dirname(__file__), "scrapers_group3"))
    module = importlib.import_module("10_si_scraper")

SIScraper = module.SIScraper

logging.basicConfig(level=logging.INFO)

async def test_si_download():
    print("="*60)
    print("🏗️  서울연구원(SI) 다운로드 테스트 시작")
    print("="*60)

    # 사용자 입력 받기
    today = datetime.now().strftime("%Y-%m-%d")
    s_input = input(f"시작 날짜 (YYYY-MM-DD, 엔터: 2026-01-01): ").strip()
    start_date = s_input if s_input else "2026-01-01"
    
    e_input = input(f"종료 날짜 (YYYY-MM-DD, 엔터: {today}): ").strip()
    end_date = e_input if e_input else today

    print(f"\n📅 대상 기간: {start_date} ~ {end_date}")
    print("-" * 60)

    scraper = SIScraper(start_date, end_date)
    
    # 실행
    await scraper.scrape()

    print("\n" + "="*60) 
    print(f"📊 수집 결과: 총 {len(scraper.results)}건")
    
    # 다운로드 폴더 확인
    download_dir = scraper.download_dir
    print(f"📂 다운로드 폴더: {download_dir}")
    if os.path.exists(download_dir):
        files = os.listdir(download_dir)
        print(f"   - 파일 개수: {len(files)}개")
        for f in files[:5]:
            print(f"   - [파일] {f}")
    else:
        print("   ⚠️ 폴더가 생성되지 않음")
    print("="*60)

if __name__ == "__main__":
    # Import workaround if needed
    try:
        module = __import__("scrapers_group3.10_si_scraper", fromlist=["SIScraper"])
        SIScraper = module.SIScraper
        asyncio.run(test_si_download())
    except ImportError:
        sys.path.append(os.path.join(os.path.dirname(__file__), "scrapers_group3"))
        import importlib
        si_module = importlib.import_module("10_si_scraper")
        SIScraper = si_module.SIScraper
        asyncio.run(test_si_download())
