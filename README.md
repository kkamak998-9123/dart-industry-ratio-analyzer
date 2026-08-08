# DART 업종별 재무비율 분석

DART Open API로 회사를 검색하면 업종을 자동 판별하고, 업종별 추천 재무비율에 필요한
계정과목을 계정 목록에서 드래그해서 매핑하면 연도별 비율을 계산·시각화해주는 웹앱입니다.

FastAPI + vanilla JS(SVG 차트, 드래그앤드롭). 원본 CLI/개발 소스는
[코딩/프로젝트 111](https://github.com/kkamak998-9123/2-/tree/add-project-111/%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8%20111) 에 있습니다.

## 로컬 실행

```
pip install -r requirements.txt
set DART_API_KEY=본인의_DART_OPEN_API_키
uvicorn main:app --reload
```

## 배포

Render `render.yaml` 기준 배포. 환경변수 `DART_API_KEY`를 Render 대시보드에서 설정해야 합니다.
