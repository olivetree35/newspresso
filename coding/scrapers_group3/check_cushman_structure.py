
import asyncio
from playwright.async_api import async_playwright

async def check_cushman(start_date=None, end_date=None):
    print(f"📅 수집 기간: {start_date} ~ {end_date}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        target_url = "https://www.cushmanwakefield.com/ko-kr/south-korea/insights"
        print(f"🚀 접속 시도: {target_url}")
        
        await page.goto(target_url, wait_until='networkidle', timeout=60000)
        
        # 조금 더 대기 (검색 엔진 초기화 시간)
        await page.wait_for_timeout(5000)
        
        print(f"✅ 접속 완료. 제목: {await page.title()}")
        
        # 1. 주요 셀렉터 확인
        selectors = [
            '.CoveoResultLink',
            '.coveo-result-link',
            'a.CoveoResultLink',
            '.card-title',
            'h3',
            'article'
        ]
        
        print("\n🔍 셀렉터 카운트:")
        for sel in selectors:
            try:
                count = await page.locator(sel).count()
                print(f"   - '{sel}': {count}개")
            except:
                print(f"   - '{sel}': 에러")
        
        # 2. iframe 여부 확인
        frames = page.frames
        print(f"\n🖼️ iframe 개수: {len(frames)}")
        
        # 3. HTML 덤프 (Body 앞부분)
        content = await page.content()
        print("\n📄 HTML 덤프 (Body Start):")
        # Body 태그 내부 1000자
        import re
        body_match = re.search(r'<body.*?>(.*)', content, re.DOTALL | re.IGNORECASE)
        if body_match:
            print(body_match.group(1)[:1000])
        else:
            print(content[:1000])

        await browser.close()

if __name__ == "__main__":
    # 한글 입출력 설정
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

    print("="*50)
    print("📅 수집 기간 설정")
    print("="*50)
    start_date_input = input("시작일을 입력하세요 (예: 2024-01-01): ").strip()
    end_date_input = input("종료일을 입력하세요 (예: 2024-12-31): ").strip()
    
    if not start_date_input or not end_date_input:
        print("❌ 시작일과 종료일을 모두 입력해야 합니다.")
    else:
        print(f"\n🚀 스크립트를 시작합니다... ({start_date_input} ~ {end_date_input})")
        asyncio.run(check_cushman(start_date_input, end_date_input))
