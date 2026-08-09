# -*- coding: utf-8 -*-
"""DART 재무제표 + 업종별 재무비율 분석 웹앱 (부모/웹 프로세스).

메모리 절감을 위해 이 프로세스는 무거운 dart_fss·pandas를 임포트하지 않는다.
- 검색/업종/추천비율: 가벼운 corp_index.json(사전 생성) + ratios.py(순수 파이썬)
- 재무제표 추출: 요청마다 analyze_worker.py를 별도 프로세스로 실행(전역 락으로 1개씩).
  워커가 종료되면 OS가 메모리를 회수하므로 부모에 메모리가 누적되지 않는다.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import ratios

BASE_DIR = Path(__file__).parent
INDEX_PATH = BASE_DIR / "data" / "corp_index.json"
BUILD_SCRIPT = BASE_DIR / "build_index.py"
WORKER_SCRIPT = BASE_DIR / "analyze_worker.py"

app = FastAPI(title="DART 업종별 재무비율 분석")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_INDEX: list[dict] = []
_INDEX_BY_CODE: dict[str, dict] = {}
_INDEX_LOCK = asyncio.Lock()      # 인덱스 최초 생성/로드 보호
_ANALYZE_LOCK = asyncio.Lock()    # 워커 프로세스 동시 1개 제한(메모리 보호)
_CACHE: dict[str, dict] = {}
_JOBS: set[str] = set()


def _load_index_file() -> bool:
    if not INDEX_PATH.exists():
        return False
    with open(INDEX_PATH, encoding="utf-8") as f:
        records = json.load(f)
    _INDEX.clear()
    _INDEX_BY_CODE.clear()
    _INDEX.extend(records)
    for r in records:
        _INDEX_BY_CODE[r["corp_code"]] = r
    return True


async def _ensure_index() -> None:
    """corp_index.json을 메모리에 적재. 없으면 build_index.py를 별도 프로세스로 생성."""
    if _INDEX:
        return
    async with _INDEX_LOCK:
        if _INDEX:
            return
        if not _load_index_file():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(BUILD_SCRIPT), str(INDEX_PATH),
                cwd=str(BASE_DIR),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()
            if proc.returncode != 0 or not _load_index_file():
                raise HTTPException(
                    status_code=503,
                    detail="검색 인덱스 생성 실패: " + (err or b"").decode("utf-8", "replace")[-300:],
                )


@app.get("/api/search")
async def search_companies(q: str = Query(..., min_length=1)):
    await _ensure_index()
    q_norm = q.strip().lower()
    matches = [
        {"corp_code": r["corp_code"], "corp_name": r["corp_name"], "stock_code": r["stock_code"]}
        for r in _INDEX
        if q_norm in r["corp_name"].lower()
    ][:20]
    return {"matches": matches}


async def _run_worker(corp_code: str) -> dict:
    """analyze_worker.py를 별도 프로세스로 1개씩 실행하고 결과 JSON을 읽는다."""
    fd, out_path = tempfile.mkstemp(suffix=".json", prefix="dart_")
    os.close(fd)
    try:
        async with _ANALYZE_LOCK:  # 동시 1개 → 부모+워커1 메모리만 존재
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(WORKER_SCRIPT), corp_code, out_path,
                cwd=str(BASE_DIR),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"error": "재무제표 분석 프로세스가 비정상 종료되었습니다(메모리 초과 등)."}
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def _build_payload(record: dict, worker_result: dict) -> dict:
    대분류 = record.get("대분류")
    추천목록 = ratios.추천비율목록(대분류 or "")
    return {
        "corp_code": record["corp_code"],
        "corp_name": record["corp_name"],
        "industry": {"대분류": 대분류, "세부업종": record.get("세부업종")},
        "statements": worker_result.get("statements", {}),
        "recommended_ratios": [r.to_json() for r in 추천목록],
    }


async def _analyze_background(corp_code: str, record: dict) -> None:
    try:
        worker_result = await _run_worker(corp_code)
        if "error" in worker_result:
            _CACHE[corp_code] = {"error": worker_result["error"]}
        else:
            _CACHE[corp_code] = _build_payload(record, worker_result)
    except Exception as e:  # noqa: BLE001
        _CACHE[corp_code] = {"error": f"분석 실패: {e}"}
    finally:
        _JOBS.discard(corp_code)


@app.get("/api/company/{corp_code}")
async def get_company_analysis(corp_code: str):
    """추출은 시간이 걸리므로 즉시 202(pending)를 반환하고 워커를 백그라운드로 돌린다.
    프론트는 완료될 때까지 짧은 간격으로 재조회(polling)한다."""
    await _ensure_index()

    if corp_code in _CACHE:
        payload = _CACHE[corp_code]
        if "error" in payload:
            raise HTTPException(status_code=502, detail=payload["error"])
        return payload

    record = _INDEX_BY_CODE.get(corp_code)
    if record is None:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    if corp_code not in _JOBS:
        _JOBS.add(corp_code)
        asyncio.create_task(_analyze_background(corp_code, record))

    return JSONResponse(status_code=202, content={"status": "pending"})


static_dir = BASE_DIR / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
