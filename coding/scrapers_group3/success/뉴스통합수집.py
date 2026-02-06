#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Group 3 통합 데이터 수집기
- 위치: scrapers_group3/success/
- 대상: KRIHS(12), KDI(13), CERIK(14), HRI(15)
"""

import sys
import os
import asyncio
import logging
import json
from datetime import datetime
import importlib.util

# 현재 파일 위치 (scrapers_group3/success/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# sys.path에 현재 디렉토리 추가 (base.py 임포트 등을 위해)
if current_dir not in sys.path:
    sys.path.append(current_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("Collector")

def load_module(name, filename):
    path = os.path.join(current_dir, filename)
    if not os.path.exists(path):
        logger.error(f"❌ 파일을 찾을 수 없습니다: {path}")
        return None
        
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None:
            logger.error(f"❌ 모듈 스펙 로드 실패: {name}")
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        logger.error(f"❌ 모듈 로딩 중 예외 발생 ({name}): {e}")
        return None

class NewsCollectorGroup3:
    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date or "2025-01-01"
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.output_dir = os.path.join(current_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.all_results = []

    async def run(self):
        logger.info("🚀 Group 3 뉴스 수집기 (통합본) 시작")
        logger.info(f"📅 수집 기간: {self.start_date} ~ {self.end_date}")
        
        # 모듈 로드 (순서: KDI -> KRIHS -> CERIK -> HRI)
        modules = [
            ("KDI", "4_kdi_scraper.py", "KDIScraper"),
            ("KRIHS", "11_krihs_scraper.py", "KRIHSScraper"),
            ("CERIK", "13_cerik_scraper.py", "CERIKScraper"),
            ("HRI", "14_hri_scraper.py", "HRIScraper")
        ]
        
        for name, filename, class_name in modules:
            mod = load_module(name.lower(), filename)
            if not mod:
                continue
                
            try:
                ScraperClass = getattr(mod, class_name)
                scraper = ScraperClass(self.start_date, self.end_date)
                
                logger.info(f"\n▶ {name} 수집 시작... ({filename})")
                
                if hasattr(scraper, 'scrape_all'):
                     await scraper.scrape_all()
                elif hasattr(scraper, 'scrape'):
                     await scraper.scrape()
                
                # 결과 수집
                if hasattr(scraper, 'results'):
                    count = len(scraper.results)
                    self.all_results.extend(scraper.results)
                    logger.info(f"   ✅ {name}: {count}건 수집 완료")
                
            except Exception as e:
                logger.error(f"❌ {name} 실행 중 오류: {e}")

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
            elif not url: # URL 없는 경우도 포함 (에러 로그용 등)
                unique_data.append(item)
                
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"group3_integrated_results_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(unique_data, f, ensure_ascii=False, indent=4)
            
        logger.info(f"💾 통합 결과 저장: {filepath} ({len(unique_data)}건)")

if __name__ == "__main__":
    if sys.platform == 'win32':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    s_date = None
    e_date = None
    
    if len(sys.argv) >= 3:
        s_date = sys.argv[1]
        e_date = sys.argv[2]
    else:
        print("\n" + "="*50)
        print("Group 3 통합 데이터 수집기")
        print("="*50)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            start_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            s_date = start_in if start_in else "2024-01-01"
            
            end_in = input(f"종료일 (YYYY-MM-DD) [기본: {today}]: ").strip()
            e_date = end_in if end_in else today
        except KeyboardInterrupt:
            sys.exit(0)

    collector = NewsCollectorGroup3(s_date, e_date)
    asyncio.run(collector.run())
