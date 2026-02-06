---
name: matplotlib-korean
description: Python 데이터 시각화(Matplotlib, Seaborn) 시 발생하는 한글 폰트 깨짐 현상을 해결하고, 한국어 시각화 코드를 작성할 때 사용하는 스킬입니다.
---

# Matplotlib Korean Helper (한글 시각화 도우미)

이 스킬은 Python으로 데이터 시각화 작업을 수행할 때 빈번히 발생하는 **한글 폰트 깨짐(네모 박스 출력)** 문제를 해결하고, 한국 사용자에게 최적화된 그래프 스타일을 제공합니다.

## 지시사항 (Instructions)

1.  **필수 폰트 설정 코드 포함**:
    - 사용자가 그래프 생성 코드를 요청하면, **반드시** 스크립트 상단(import 직후)에 아래의 OS 맞춤형 폰트 설정 코드를 삽입하십시오.

    ```python
    import matplotlib.pyplot as plt
    import platform

    # 시스템 환경에 따른 한글 폰트 설정
    system_name = platform.system()
    if system_name == 'Windows':
        plt.rc('font', family='Malgun Gothic') # 윈도우: 맑은 고딕
    elif system_name == 'Darwin':
        plt.rc('font', family='AppleGothic') # 맥: 애플고딕
    else:
        # 리눅스 등: 나눔고딕 (설치 필요 시 주석 안내)
        plt.rc('font', family='NanumGothic')

    # 마이너스 부호 깨짐 방지
    plt.rc('axes', unicode_minus=False)
    ```

2.  **한국어 친화적 포맷팅**:
    - **단위**: 큰 숫자는 '100만', '1조' 등 한국인이 익숙한 단위로 변환하여 축(Axis)나 툴팁에 표시하는 로직을 고려하십시오.
    - **날짜**: 'YYYY-MM-DD' 또는 'YYYY년 MM월' 등 한국 표준 날짜 형식을 사용하십시오.
    - **제목 및 라벨**: 그래프 제목, 축 이름, 범례는 명확한 한국어로 작성하십시오.

3.  **환경별 대응 (Colab/Jupyter)**:
    - 코랩(Google Colab) 환경으로 의심되는 경우, 폰트 설치(`!sudo apt-get install...`)와 캐시 삭제 코드를 주석이나 별도 셀로 안내하십시오.

## 제약조건 (Constraints)

- 사용자가 특정 영문 폰트를 지정하지 않는 한, 기본적으로 한글 폰트 설정을 우선 적용합니다.
- Seaborn 사용 시에도 `sns.set(font='Malgun Gothic', ...)` 형태로 폰트가 적용되도록 하십시오.

## 예시 (Examples)

**사용자**: "매출 추이 그래프 그려줘"

**에이전트 생성 코드**:
```python
import pandas as pd
import matplotlib.pyplot as plt
import platform

# 1. 한글 폰트 설정
if platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')
plt.rc('axes', unicode_minus=False)

# 2. 데이터 준비
data = {'월': ['1월', '2월', '3월'], '매출': [100, 150, 130]}
df = pd.DataFrame(data)

# 3. 시각화
plt.figure(figsize=(10, 6))
plt.plot(df['월'], df['매출'], marker='o')
plt.title('2024년 월별 매출 추이')
plt.xlabel('기간')
plt.ylabel('매출 (단위: 억 원)')
plt.grid(True)
plt.show()
```
