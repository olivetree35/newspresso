"""
Supabase 연결 설정 및 사용 예제
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# .env.local 파일에서 환경변수 로드
load_dotenv('.env.local')

class SupabaseManager:
    """Supabase 데이터베이스 관리 클래스"""
    
    def __init__(self):
        """Supabase 클라이언트 초기화"""
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError(
                "Supabase URL과 KEY가 설정되지 않았습니다. "
                ".env.local 파일을 확인해주세요."
            )
        
        self.client: Client = create_client(url, key)
    
    def insert_data(self, table_name: str, data: dict):
        """
        데이터 삽입
        
        Args:
            table_name: 테이블 이름
            data: 삽입할 데이터 (딕셔너리)
        
        Returns:
            삽입된 데이터
        """
        try:
            response = self.client.table(table_name).insert(data).execute()
            print(f"✅ 데이터 삽입 성공: {table_name}")
            return response.data
        except Exception as e:
            print(f"❌ 데이터 삽입 실패: {e}")
            raise
    
    def select_data(self, table_name: str, filters: dict = None):
        """
        데이터 조회
        
        Args:
            table_name: 테이블 이름
            filters: 필터 조건 (딕셔너리, 선택사항)
        
        Returns:
            조회된 데이터 리스트
        """
        try:
            query = self.client.table(table_name).select("*")
            
            # 필터가 있으면 적용
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            response = query.execute()
            print(f"✅ 데이터 조회 성공: {len(response.data)}개 항목")
            return response.data
        except Exception as e:
            print(f"❌ 데이터 조회 실패: {e}")
            raise
    
    def update_data(self, table_name: str, filters: dict, data: dict):
        """
        데이터 업데이트
        
        Args:
            table_name: 테이블 이름
            filters: 업데이트할 레코드를 찾기 위한 필터
            data: 업데이트할 데이터
        
        Returns:
            업데이트된 데이터
        """
        try:
            query = self.client.table(table_name).update(data)
            
            # 필터 적용
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.execute()
            print(f"✅ 데이터 업데이트 성공")
            return response.data
        except Exception as e:
            print(f"❌ 데이터 업데이트 실패: {e}")
            raise
    
    def delete_data(self, table_name: str, filters: dict):
        """
        데이터 삭제
        
        Args:
            table_name: 테이블 이름
            filters: 삭제할 레코드를 찾기 위한 필터
        
        Returns:
            삭제된 데이터
        """
        try:
            query = self.client.table(table_name).delete()
            
            # 필터 적용
            for key, value in filters.items():
                query = query.eq(key, value)
            
            response = query.execute()
            print(f"✅ 데이터 삭제 성공")
            return response.data
        except Exception as e:
            print(f"❌ 데이터 삭제 실패: {e}")
            raise


# 사용 예제
if __name__ == "__main__":
    # Supabase 매니저 초기화
    db = SupabaseManager()
    
    # 예제 1: 데이터 삽입
    # new_report = {
    #     "title": "테스트 리포트",
    #     "date": "2024-01-01",
    #     "url": "https://example.com/report.pdf",
    #     "site_name": "테스트 사이트"
    # }
    # db.insert_data("reports", new_report)
    
    # 예제 2: 데이터 조회
    # all_reports = db.select_data("reports")
    # print(f"전체 리포트 수: {len(all_reports)}")
    
    # 예제 3: 필터링된 데이터 조회
    # filtered_reports = db.select_data("reports", {"site_name": "테스트 사이트"})
    # print(f"필터링된 리포트 수: {len(filtered_reports)}")
    
    # 예제 4: 데이터 업데이트
    # db.update_data(
    #     "reports",
    #     {"title": "테스트 리포트"},
    #     {"title": "업데이트된 리포트"}
    # )
    
    # 예제 5: 데이터 삭제
    # db.delete_data("reports", {"title": "업데이트된 리포트"})
    
    print("✨ Supabase 연결 설정이 완료되었습니다!")
