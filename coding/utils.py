import csv
import os
from typing import List, Dict

def save_to_csv(results: List[Dict], site_code: str, output_dir: str = "output"):
    """
    수집 결과를 CSV 파일로 저장
    """
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)
    
    # 타임스탬프 기반 파일명
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{site_code}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    try:
        # 모든 키 수집 (필드 확정)
        all_keys = set().union(*(d.keys() for d in results))
        
        # 주요 컬럼 우선 순위
        priority = ['source', 'title', 'date', 'pdf_url', 'page_url', 'collected_at']
        fieldnames = [k for k in priority if k in all_keys] + [k for k in all_keys if k not in priority]
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
            
        print(f"💾 CSV 저장 완료: {filepath}")
        
    except Exception as e:
        print(f"❌ CSV 저장 실패: {e}")
