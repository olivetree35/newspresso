import os
import subprocess
import sys
import re
from datetime import datetime

# 한글 출력 설정
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 전역 변수 초기화
SUCCESS_DIR = r"d:\Antigravity\coding\scrapers_group3\success"
START_DATE = "2024-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")

def run_scraper(file_path):
    filename = os.path.basename(file_path)
    print(f"Testing {filename}...")
    
    cmd = [sys.executable, file_path, START_DATE, END_DATE]
    try:
        # 타임아웃 120초
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='ignore')
        output = result.stdout + "\n" + result.stderr
        
        # 건수 추출
        match = re.search(r'(\d+)건\s*수집', output)
        if not match:
            match = re.search(r'수집\s*완료:\s*(?:총\s*)?(\d+)건', output)
            
        count = match.group(1) if match else "0"
        status = "✅ 성공" if result.returncode == 0 else "❌ 실패"
        
        if count == "0" and result.returncode == 0:
            status = "⚠️ 0건 (성공)"
            
        print(f"  -> {status} ({count}건)")
        return status, count
        
    except subprocess.TimeoutExpired:
        print(f"  -> 🕒 시간 초과")
        return "🕒 타임아웃", "N/A"
    except Exception as e:
        print(f"  -> ❌ 에러: {str(e)}")
        return "❌ 에러", "0"

def main():
    global START_DATE, END_DATE
    
    if sys.platform == "win32":
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass

    # 1. 인자 확인
    if len(sys.argv) >= 3:
        START_DATE = sys.argv[1]
        END_DATE = sys.argv[2]
    else:
        # 2. 대화형 입력
        print("\n" + "="*50)
        print("전체 스크래퍼 검증/실행 도구")
        print("="*50)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            s_in = input("시작일 (YYYY-MM-DD) [기본: 2024-01-01]: ").strip()
            if s_in: START_DATE = s_in
            
            e_in = input(f"종료일 (YYYY-MM-DD) [기본: {today}]: ").strip()
            if e_in: END_DATE = e_in
        except KeyboardInterrupt:
            sys.exit(0)

    files = [f for f in os.listdir(SUCCESS_DIR) if f.endswith("_scraper.py")]
    # 숫자순 정렬
    def get_num(name):
        try: return int(name.split('_')[0])
        except: return 999
    files.sort(key=get_num)
    
    results = []
    print(f"\n[ 전체 스크래퍼 검증 시작 ]")
    print(f"기간: {START_DATE} ~ {END_DATE}")
    print("-" * 50)
    
    for f in files:
        f_path = os.path.join(SUCCESS_DIR, f)
        status, count = run_scraper(f_path)
        results.append({
            "num": f.split('_')[0],
            "name": f,
            "status": status,
            "count": count
        })
        
    print("\n\n" + "="*80)
    print(f"{'No':<5} | {'파일명':<25} | {'결과':<15} | {'수집건수':<10}")
    print("-" * 80)
    for r in results:
        print(f"{r['num']:<5} | {r['name']:<25} | {r['status']:<15} | {r['count']:<10}")
    print("="*80)

if __name__ == "__main__":
    main()
