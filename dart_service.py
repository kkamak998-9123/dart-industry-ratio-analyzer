"""DART 회사 검색, 재무제표 추출/가공 (웹 API용).

CLI 버전(../dart_service.py)과 로직은 동일하되, 대화형 input() 대신
검색 결과를 그대로 반환하고, 재무제표를 JSON 직렬화 가능한 형태로 가공한다.
"""

import os

import dart_fss as dart
import pandas as pd

from utils import 연결여부, 연도_라벨

API_KEY = os.environ.get("DART_API_KEY")
if not API_KEY:
    raise RuntimeError("DART_API_KEY 환경변수를 설정해주세요.")
dart.set_api_key(api_key=API_KEY)

IS_LIKE_YEAR_PATTERN = r"label_ko|\d{8}-\d{8}"
BS_YEAR_PATTERN = r"label_ko|\d{8}"


class 재무데이터없음(Exception):
    pass


_corp_list = None


def 회사목록():
    global _corp_list
    if _corp_list is None:
        _corp_list = dart.get_corp_list()
    return _corp_list


def 회사검색(name: str, limit: int = 20):
    목록 = 회사목록()
    후보 = 목록.find_by_corp_name(name, exactly=False, market="YK") or []
    return list(후보[:limit])


def 회사_by_code(corp_code: str):
    목록 = 회사목록()
    return 목록.find_by_corp_code(corp_code)


def 재무제표추출(corp_code: str, bgn_de="20230101", end_de="20261231"):
    """dataset='web': XBRL(arelle) 대신 DART 재무제표 뷰어에서 추출해 메모리 절감.
    bgn_de='20230101'로 최근 연간보고서만 가져와 약 5개년을 확보한다.
    corp_list가 없어도 corp_code 문자열만으로 동작한다."""
    return dart.fs.extract(corp_code=corp_code, bgn_de=bgn_de, end_de=end_de, dataset="web")


def _통합조회(재무제표, keys, 에러메시지):
    for key in keys:
        table = 재무제표[key]
        if table is not None:
            return table
    raise 재무데이터없음(에러메시지)


def 손익계산서_가공(재무제표):
    표 = _통합조회(재무제표, ["is", "cis"], "손익계산서/포괄손익계산서 항목이 없습니다.")
    return 표.filter(regex=IS_LIKE_YEAR_PATTERN)


def 재무상태표_가공(재무제표):
    표 = _통합조회(재무제표, ["bs"], "재무상태표 항목이 없습니다.")
    return 표.filter(regex=BS_YEAR_PATTERN)


def 현금흐름표_가공(재무제표):
    표 = _통합조회(재무제표, ["cf", "ccf"], "현금흐름표/연결현금흐름표 항목이 없습니다.")
    return 표.filter(regex=IS_LIKE_YEAR_PATTERN)


def _연도별_컬럼(df: pd.DataFrame) -> dict:
    """{연도: (실제컬럼, 연결여부)} - 연결/별도가 동시에 있으면 연결 우선"""
    연도별 = {}
    for col in df.columns[1:]:
        연도 = 연도_라벨(col)
        연결 = 연결여부(col)
        if 연도 not in 연도별 or (연결 and not 연도별[연도][1]):
            연도별[연도] = (col, 연결)
    return 연도별


def 통계_페이로드(df: pd.DataFrame, max_years: int = 5) -> dict:
    """가공된 재무제표 df를 프론트엔드가 바로 쓸 수 있는 JSON 구조로 변환.

    {"years": ["2021", ...], "items": [{"label": "매출액", "values": {"2021": 1000.0}}]}
    max_years: 최근 N개년만 유지(기본 5). 종목에 따라 6개년이 잡혀도 5개년으로 절삭.
    """
    label_col = df.columns[0]
    연도별컬럼 = _연도별_컬럼(df)
    정렬된연도 = sorted(연도별컬럼)[-max_years:]

    items = []
    for _, row in df.iterrows():
        label = row[label_col]
        if not isinstance(label, str) or not label.strip():
            continue
        values = {}
        for 연도 in 정렬된연도:
            col, _ = 연도별컬럼[연도]
            try:
                value = float(row[col])
            except (TypeError, ValueError):
                continue
            if pd.isna(value):
                continue
            values[연도] = value
        if values:
            items.append({"label": label, "values": values})

    return {"years": 정렬된연도, "items": items}
