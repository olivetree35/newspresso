import sys
import os
import asyncio
import logging

# 경로 설정
sys.path.append(os.path.join(os.path.dirname(__file__), "scrapers_group3"))

from scrapers_group3 import kdi

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        scraper = kdi.KDIScraper("2025-12-01", "2026-01-31")
        await scraper.scrape()
        print(f"수집 결과: {len(scraper.results)}건")
        for res in scraper.results:
            print(res)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
