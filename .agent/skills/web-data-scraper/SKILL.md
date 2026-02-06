---
name: web-data-scraper
description: 웹사이트 데이터 수집을 위한 스크래퍼 개발 및 통합 워크플로우 스킬. 사이트별 수집 로직 구현부터 성공 파일 이동, 정렬, 사용자 검증까지의 전체 프로세스를 정의함.
---

# 웹 데이터 스크래퍼 & 통합 워크플로우 (Group 3 Rule)

이 스킬은 `D:\Antigravity\coding\scrapers_group3` 프로젝트에서 스크래퍼를 순차적으로 개발하고 정리하는 **표준 절차(SOP)**입니다.

---

## � 핵심 반복 작업 워크플로우 (Mandatory Process)

모든 스크래퍼 개발은 아래 4단계 프로세스를 엄격히 따릅니다.

### 1단계: 타겟 선정 (Target Selection)

- **기준 파일**: `D:\Antigravity\coding\scrapers_group3\news_collector_group3.py`
- **규칙**:
  1. 위 파일의 `RESEARCH_SITES` 리스트 순서를 확인합니다.
  2. 현재 `success` 폴더에 없는 **가장 첫 번째 순서의 사이트**를 다음 작업 대상으로 선정합니다.

### 2단계: 개발 및 자율 실행 (Autonomous Development)

- **자율성 모드**: **ON (Accept All)**
- **행동 지침**:
  1. 대상 사이트의 구조를 분석하고 코드를 작성합니다.
  2. 에러가 발생하면 **사용자에게 묻지 않고 스스로 수정(Debug)**합니다.
  3. `run_command`를 적극 사용하여 코드를 실행하고 테스트합니다.
  4. **성공 기준**:
     - 에러 없이 실행 종료.
     - `title`, `date`, `download_url` 등의 필수 데이터가 추출됨.
     - 결과값이 `output` 폴더에 JSON 등으로 저장됨.

### 3단계: 파일 정리 및 정렬 (File Management)

- **이동 경로**: `D:\Antigravity\coding\scrapers_group3\success`
- **파일명 규칙**: `[순서번호]_[사이트식별자]_scraper.py`
  - **순서번호**: 통합 수집기 리스트(`news_collector_group3.py`) 상의 순서를 따름 (1부터 시작).
  - **예시**: 리스트의 4번째 사이트라면 -> `4_kdi_scraper.py`
  - 이미 `success` 폴더에 파일이 있다면, 중복되지 않게 순서를 맞춰서 정렬합니다.

### 4단계: 검증 및 대기 (Verification & Halt)

- **자율성 모드**: **OFF (Wait for User)**
- **행동 지침**:
  1. 하나의 파일 개발과 이동이 완료되면 즉시 **작업을 멈춥니다.**
  2. 사용자에게 "00번 스크래퍼 개발 완료. 결과를 확인해주세요."라고 보고합니다.
  3. **사용자의 OK(승인) 서명**이 있을 때까지 다음 사이트로 넘어가지 않습니다.

---

## 📈 지속적 개선 (Continuous Improvement)

**"새로운 기술이나 패턴 발견 시 즉시 업데이트하라."**

작업 수행 중 더 효율적인 방법, 새로운 다운로드 패턴, 혹은 범용적인 해결책(Skill)을 발견하면, **이 문서를 스스로 업데이트**해야 합니다.

1. **패턴 발견**: 예) "iframe 내부의 PDF 링크 추출 패턴", "특정 보안 솔루션 우회법" 등.
2. **문서 갱신**: 발견 즉시 `SKILL.md`의 "다운로드 URL 추출 전략"이나 "코드 가이드라인" 섹션에 내용을 추가합니다.
3. **효율화**: 이후 작업에서는 갱신된 지식을 활용하여 시행착오를 줄이고 개발 속도를 높입니다.

---

## 코드 작성 가이드라인 (Coding Standard)

### 1. 필수 수집 항목

| 변수명 | 설명 |
|--------|------|
| `title` | 게시글/리포트 제목 |
| `date` | 작성일 (YYYY-MM-DD) |
| `site_name` | 출처 (한글명) |
| `download_url` | **원문/PDF 다운로드 링크** (필수) |

### 2. 코드 구조 템플릿

- **Playwright (Async) 권장**: 동적 페이지 및 네트워크 캡처에 유리함.
- **주석**: 섹션별 설명은 반드시 **한국어**로 작성.
- **마지막 줄**: `if __name__ == "__main__":` 블록을 두어 단독 실행 테스트가 가능해야 함.

### 3. 다운로드 URL 추출 전략 (우선순위)

1. **Network Response**: `.pdf` 요청이나 `Content-Disposition` 헤더 감지.
2. **Onclick Parsing**: `onclick="location.href='...'"` 등의 자바스크립트 내 URL 추출.
3. **HTML Attribute**: `src`, `href`, `data-file` 등 속성값 직접 추출.

---

## � 디렉토리 구조

- **Root**: `D:\Antigravity\coding\scrapers_group3`
- **Success (완료본)**: `D:\Antigravity\coding\scrapers_group3\success`
- **Output (결과물)**: `D:\Antigravity\coding\scrapers_group3\success\output` (또는 상위 output)

---

## ⚠️ 에러 핸들링 & 봇 탐지 우회

- **User-Agent**: 필수적으로 실제 브라우저 UA 설정.
- **Delay**: 페이지 이동 간 `wait_for_timeout(2000)` 이상 랜덤 딜레이 권장.
- **Retry**: `try-except` 블록으로 개별 항목 에러가 전체 중단을 막도록 처리.

---

## 📚 트러블슈팅 사례 연구 (Case Study: Cushman & Wakefield)

**"동적 로딩이 심하고 Selector가 불확실한 사이트 해결 전략"**

### 1. 실패 원인 분석 (Why It Failed)

이번 디버깅에서 발견된 4가지 핵심 문제는 스크래핑뿐만 아니라 '기본적인 코딩 실수'와 '복잡한 DOM 구조'가 복합된 사례입니다.

1. **기초적인 런타임 에러**:
    - `import json` 누락 → `NameError`로 인해 저장 단계에서 실패.
    - 변수(`collected_count`) 초기화 위치가 `try` 블록 내부 → 예외 발생 시 `UnboundLocalError` 발생.
2. **Selector 의존성 실패**:
    - `CoveoResultLink` 클래스가 메인 프레임에 존재하지 않거나, 로딩 지연/Shadow DOM 문제로 `timeout` 발생.
    - Playwright 전용 문법(`:text-matches`)과 CSS Selector 혼용 시 구문 에러 리스크.
3. **논리적 누락**:
    - iframe 탐색 로직은 추가했으나, 정작 '메인 프레임'에서 찾은 데이터를 리스트에 넣는 로직이 누락되어 데이터가 있어도 0건으로 처리됨.

### 2. 해결 솔루션 (Solution)

**A. Brute Force (전수 조사) 전략 도입**

- 특정 클래스(`.items`, `.list`)를 찾으려 애쓰지 말고, **모든 `<a>` 태그를 일단 가져옴**.
- Python 코드 레벨에서 `href`나 `text`에 **핵심 키워드(report, pdf, 다운로드, outlook 등)**가 포함되었는지 필터링.
- **장점**: 사이트의 HTML 구조(클래스명 등)가 변경되거나 난독화되어도 '링크'와 '텍스트'는 유지되므로 매우 강력함.

**B. 방어적 코딩 (Defensive Coding)**

- **Import 체크**: `json`, `os`, `re` 등 필수 라이브러리는 파일 최상단에서 확인.
- **스코프 관리**: 카운터나 결과 리스트 같은 핵심 변수는 반드시 **함수 최상단(try문 밖)**에서 초기화.

**C. 다층 탐색 (Multi-layer Search)**

- 메인 프레임 탐색 실패 시 -> `page.frames` 루프를 통해 모든 iframe 내부 탐색 -> 그래도 없으면 Brute Force 실행.
- 이 순차적 전략(Fallback Strategy)을 통해 놓치는 데이터를 최소화함.

---

## 📚 트러블슈팅 사례 연구 (Case Study: IBK Investment & Securities)

**"정적 라이브러리(Requests)의 한계와 프로토콜 이슈 극복"**

### 1. 실패 원인 분석 (Why It Failed)

1. **정적 수집의 한계**:
    - 초기에 가벼운 `requests` + `BeautifulSoup` 조합을 사용했으나, 사이트가 리스트를 JavaScript로 동적 렌더링하여 HTML 소스에 데이터가 없었음. (빈 껍데기만 수집됨)
2. **프로토콜/네트워크 이슈**:
    - `https://`로 접속 시 무한 대기(Timeout) 또는 SSL 핸드쉐이크 에러가 발생하여 접속조차 불가능했음.

### 2. 해결 솔루션 (Solution)

**A. 빠른 태세 전환 (Pivot to Playwright)**

- **Rule**: `view-source:`(소스보기)와 개발자 도구의 Element 탭 내용이 확연히 다르다면, 즉시 `Playwright`나 `Selenium` 같은 브라우저 자동화 도구로 전환해야 함.
- 동적 사이트에서 `requests`로 헤더를 조작하며 시간을 낭비하는 것보다, 실제 브라우저를 띄우는 것이(headless 모드) 훨씬 효율적임.

**B. 프로토콜 유연성 (Protocol Flexibility)**

- **HTTP Fallback**: 보안 설정이 강하거나, 혹은 반대로 서버 설정이 미흡한 레거시 사이트의 경우 `https` 대신 `http`로 접속을 시도하여 해결.
- **SSL 무시**: Playwright 실행 시 `ignore_https_errors=True` 옵션을 기본값처럼 사용하여 인증서 문제를 우회.

**C. 복합 Selector 전략**

- 단순한 태그(`.subject`)만 찾지 말고, 구조적 관계를 이용 (`li:has(.subject)`)하여 정확한 아이템 단위를 식별.
- 다운로드 버튼이 `<a>` 태그가 아닌 `<img>` 태그에 클릭 이벤트가 걸린 경우(`onclick`), 상위 요소를 찾거나 JS 실행을 고려.

---

## 📚 트러블슈팅 사례 연구 (Case Study: Kyobo Realco)

**"유령 문자열(Ghost Text)과 JSHandle 접근 불가 해결"**

### 1. 실패 원인 분석 (Why It Failed)

1. **유령 문자열 (Ghost Text)**:
    - 다운로드 아이콘(`<a><i></i></a>`)을 찾았으나, 해당 요소의 부모(`li`)나 조상(`tr`)에 텍스트 노드가 전혀 없음.
    - 실제로는 형제 요소(`li` 옆의 다른 `li`)에 텍스트가 존재하나, `closest`로 찾은 직계 조상에는 텍스트가 없는 구조적 분리 현상.
2. **JSHandle 접근 불가**:
    - `await row.innerText()` 방식은 `ElementHandle`에서만 가능하며, `JSHandle`(evaluate_handle의 반환값)에서는 사용할 수 없음.
    - 무리하게 접근 시 `AttributeError` 또는 `null` 참조 에러 발생.

### 2. 해결 솔루션 (Solution)

**A. 탐색 범위 확장 (Scope Expansion)**

- `closest('tr')`이나 `closest('li')`가 실패하거나 텍스트가 비어있다면(`Empty Text`), 더 상위 컨테이너인 **`closest('ul')`** 또는 `div.list_item`까지 범위를 넓혀 탐색.
- 전체 '행(Row)'을 감싸는 컨테이너를 잡아야 흩어진 형제 요소들의 텍스트(제목, 날짜)를 한 번에 가져올 수 있음.

**B. 안전한 평가 (Safe Evaluation)**

- 파이썬 객체로 변환하려 하지 말고, 브라우저 컨텍스트 내에서 JS로 값을 추출.
- **Pattern**: `value = await handle.evaluate("el => el ? (el.innerText || el.textContent) : ''")`
- `innerText`가 안 될 경우 숨겨진 텍스트일 수 있으므로 `textContent`를 OR(`||`) 조건으로 함께 검사.
