#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토연구원(KRIHS) 스크래퍼 테스트
"""

import asyncio
import sys
import os
import logging
import importlib
from datetime import datetime, timedelta

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 sys.path에 추가 (scrapers_group3가 있는 폴더)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)

async def test_krihs():
    print("="*60)
    print("🏗️  국토연구원(KRIHS) 스크래퍼 테스트 시작")
    print("="*60)

    # 모듈 동적 로드 (파일명이 숫자로 시작하므로)
    # d:\Antigravity\coding\scrapers_group3\11_krihs_scraper.py
    try:
        # 패키지 내 모듈로 로드 시도
        module = importlib.import_module("scrapers_group3.11_krihs_scraper")
    except ImportError:
        # 실패 시 경로를 직접 추가하여 로드
        scrapers_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapers_group3")
        sys.path.append(scrapers_path)
        module = importlib.import_module("11_krihs_scraper")

    KRIHSScraper = module.KRIHSScraper

    # 테스트 기간: 2026년 (최신 데이터 수집 확인)
    start_date = "2026-01-01"
    end_date = "2026-12-31"

    print(f"📅 대상 기간: {start_date} ~ {end_date}")

    scraper = KRIHSScraper(start_date, end_date)
    await scraper.scrape()

    print("\n" + "="*60) 
    print(f"📊 수집 결과: 총 {len(scraper.results)}건")
    if scraper.results:
        print(f"   [첫번째 항목] {scraper.results[0]['title']}")
        print(f"   [날짜] {scraper.results[0]['date']}")
        print(f"   [PDF  URL] {scraper.results[0]['pdf_url']}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_krihs())
