#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Group 3 통합 데이터 수집기
- 대상 사이트: KRIHS(국토연구원), KDI(한국개발연구원), CERIK(한국건설산업연구원), HRI(현대경제연구원)
- 기능: 각 전용 스크래퍼 모듈을 실행하여 데이터를 수집하고 하나의 결과로 통합
"""

import sys
import os
import asyncio
import logging
import json
from datetime import datetime

# 현재 파일 위치 (success/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 스크래퍼 모듈 경로 (success/scrapers_group3/)
scrapers_dir = os.path.join(current_dir, "scrapers_group3")

# sys.path에 추가
if scrapers_dir not in sys.path:
    sys.path.append(scrapers_dir)

# 동적으로 모듈 임포트
import importlib.util

def load_module(name, path):
    if not os.path.exists(path):
        # 만약 scrapers_group3 폴더가 이중으로 있거나 경로가 다르면 찾아보기
        # 예: success/scrapers_group3/success/scrapers_group3 ? (사용자가 mv를 여러번 했을 수도 있음)
        # 일단 기본 경로 시도
        pass
        
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise ImportError(f"모듈을 찾을 수 없습니다: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# 경로 설정 (파일명 확인 필요)
# KRIHS: 10_1_krihs_scraper.py
# KDI: kdi.py
# CERIK: 14_cerik_scraper.py
# HRI: 15_hri_scraper.py

try:
    krihs_path = os.path.join(scrapers_dir, "10_1_krihs_scraper.py")
    if not os.path.exists(krihs_path): # 파일명이 다를 경우 대비
         krihs_path = os.path.join(scrapers_dir, "12_krihs_scraper.py")
         
    krihs_mod = load_module("krihs", krihs_path)
    kdi_mod = load_module("kdi", os.path.join(scrapers_dir, "kdi.py"))
    cerik_mod = load_module("cerik", os.path.join(scrapers_dir, "14_cerik_scraper.py"))
    hri_mod = load_module("hri", os.path.join(scrapers_dir, "15_hri_scraper.py"))

    KRIHSScraper = krihs_mod.KRIHSScraper
    KDIScraper = kdi_mod.KDIScraper
    CERIKScraper = cerik_mod.CERIKScraper
    HRIScraper = hri_mod.HRIScraper

except Exception as e:
    print(f"❌ 모듈 로딩 실패: {e}")
    # 디렉토리 목록 출력해서 디버깅
    print(f"📂 {scrapers_dir} 목록:")
    try:
        for f in os.listdir(scrapers_dir):
            print(f" - {f}")
    except:
        print(" (디렉토리를 읽을 수 없음)")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("Collector")

class NewsCollectorGroup3:
    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date or "2025-01-01"
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.output_dir = os.path.join(current_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.all_results = []

    async def run(self):
        logger.info("🚀 Group 3 뉴스 수집기 시작")
        logger.info(f"📅 수집 기간: {self.start_date} ~ {self.end_date}")
        
        scrapers = [
            ("KRIHS (국토연구원)", KRIHSScraper(self.start_date, self.end_date)),
            ("KDI (한국개발연구원)", KDIScraper(self.start_date, self.end_date)),
            ("CERIK (한국건설산업연구원)", CERIKScraper(self.start_date, self.end_date)),
            ("HRI (현대경제연구원)", HRIScraper(self.start_date, self.end_date))
        ]
        
        for name, scraper in scrapers:
            try:
                logger.info(f"\n▶ {name} 수집 시작...")
                if hasattr(scraper, 'scrape_all'):
                     await scraper.scrape_all()
                elif hasattr(scraper, 'scrape'):
                     await scraper.scrape()
                else:
                    logger.error(f"❌ {name}: 실행 메서드를 찾을 수 없음")
                    continue
                
                # 결과 수집
                if hasattr(scraper, 'results'):
                    self.all_results.extend(scraper.results)
                    logger.info(f"   ✅ {len(scraper.results)}건 수집 완료")
                
            except Exception as e:
                logger.error(f"❌ {name} 수집 중 오류: {e}")
                import traceback
                traceback.print_exc()

        self.save_integrated_results()
        logger.info("\n✨ 모든 수집 작업 완료!")

    def save_integrated_results(self):
        if not self.all_results:
            logger.warning("⚠️ 수집된 데이터가 없습니다.")
            return

        # 중복 제거 (download_url 기준)
        seen = set()
        unique_data = []
        for item in self.all_results:
            url = item.get('download_url')
            if url and url not in seen:
                seen.add(url)
                unique_data.append(item)
                
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"group3_integrated_results_{timestamp}.json"
        
        # output 폴더가 없으면 생성 (생성자에서도 하지만 안전하게)
        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(unique_data, f, ensure_ascii=False, indent=4)
            
        logger.info(f"💾 통합 결과 저장: {filepath} ({len(unique_data)}건)")

if __name__ == "__main__":
    if len(sys.argv) == 3:
        s_date, e_date = sys.argv[1], sys.argv[2]
    else:
        s_date = "2025-12-01"
        e_date = "2026-01-31"

    collector = NewsCollectorGroup3(s_date, e_date)
    asyncio.run(collector.run())
