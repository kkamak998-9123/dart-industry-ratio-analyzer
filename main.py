# -*- coding: utf-8 -*-
"""DART 재무제표 + 업종별 재무비율 분석 웹앱: API + 정적 프론트엔드"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import dart_service
import ratios
from industry import 업종분류기

app = FastAPI(title="DART 업종별 재무비율 분석")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

업종분류 = 업종분류기()
_CACHE: dict[str, dict] = {}
_JOBS: set[str] = set()  # 현재 백그라운드에서 분석 중인 corp_code


@app.get("/api/search")
def search_companies(q: str = Query(..., min_length=1)):
    후보 = dart_service.회사검색(q)
    return {
        "matches": [
            {"corp_code": c.corp_code, "corp_name": c.corp_name, "stock_code": getattr(c, "stock_code", None)}
            for c in 후보
        ]
    }


def _분석_수행(회사) -> dict:
    try:
        원본재무제표 = dart_service.재무제표추출(회사)
    except Exception as e:
        return {"error": f"DART 재무제표 추출 실패: {e}"}

    statements = {}
    for key, 가공함수 in [
        ("is", dart_service.손익계산서_가공),
        ("bs", dart_service.재무상태표_가공),
        ("cf", dart_service.현금흐름표_가공),
    ]:
        try:
            df = 가공함수(원본재무제표)
            statements[key] = dart_service.통계_페이로드(df)
        except dart_service.재무데이터없음 as e:
            statements[key] = {"years": [], "items": [], "error": str(e)}

    대분류명, 세부업종명 = 업종분류.분류(getattr(회사, "sector", None))
    추천목록 = ratios.추천비율목록(대분류명 or "")

    return {
        "corp_code": 회사.corp_code,
        "corp_name": 회사.corp_name,
        "industry": {"대분류": 대분류명, "세부업종": 세부업종명},
        "statements": statements,
        "recommended_ratios": [r.to_json() for r in 추천목록],
    }


async def _분석_백그라운드(corp_code: str, 회사) -> None:
    try:
        _CACHE[corp_code] = await asyncio.to_thread(_분석_수행, 회사)
    finally:
        _JOBS.discard(corp_code)


@app.get("/api/company/{corp_code}")
async def get_company_analysis(corp_code: str):
    """DART 조회는 종목에 따라 1~3분 걸릴 수 있어 프록시 타임아웃(수십 초)을
    넘기기 쉽다. 그래서 즉시 응답하지 않고 백그라운드로 돌리며, 준비 전에는
    202(pending)를 반환해 프론트에서 짧은 간격으로 재조회(polling)하게 한다."""
    if corp_code in _CACHE:
        payload = _CACHE[corp_code]
        if "error" in payload:
            raise HTTPException(status_code=502, detail=payload["error"])
        return payload

    if corp_code not in _JOBS:
        회사 = dart_service.회사_by_code(corp_code)
        if 회사 is None:
            raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
        _JOBS.add(corp_code)
        asyncio.create_task(_분석_백그라운드(corp_code, 회사))

    return JSONResponse(status_code=202, content={"status": "pending"})


static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
