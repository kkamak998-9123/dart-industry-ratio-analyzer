"""통계청 KSIC(11차) 연계표 기반 업종 분류 모듈.

DART의 회사별 sector 문자열을 표준산업분류 대분류/중분류로 정규화한다.
"""

import os
import re

import pandas as pd

_EXCEL_PATH = os.path.join(os.path.dirname(__file__), "data", "2. 한국표준산업분류표(제11차).xlsx")

_COLUMNS = [
    "대분류코드", "대분류명", "중분류코드", "중분류명",
    "소분류코드", "소분류명", "세분류코드", "세분류명",
    "세세분류코드", "세세분류명",
]


def _clean_text(s) -> str:
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"[ㆍ·\s;,\.~/\(\)\-]", "", s)
    s = s.replace("나", "및")
    return s


def _표시명_정리(name: str) -> str:
    if not isinstance(name, str):
        return name
    return re.sub(r"\([^)]*\)\s*$", "", name).strip()


class 업종분류기:
    """KSIC 매핑표를 1회 로드해두고 dart sector 문자열 -> 업종 정보를 조회한다."""

    def __init__(self, excel_path: str = _EXCEL_PATH):
        self._lookup: dict[str, tuple[str, str, str]] = {}
        self._loaded = False
        self._load(excel_path)

    def _load(self, excel_path: str):
        if not os.path.exists(excel_path):
            return

        df = pd.read_excel(excel_path, sheet_name="11차개정한국표준산업분류", header=1)
        df.columns = _COLUMNS
        ffill_cols = _COLUMNS[:8]
        df[ffill_cols] = df[ffill_cols].ffill()

        for _, row in df.iterrows():
            대분류명, 중분류명, 대분류코드 = row["대분류명"], row["중분류명"], row["대분류코드"]
            for col in ["소분류명", "중분류명", "세분류명", "세세분류명"]:
                key = _clean_text(row[col])
                if key and key not in self._lookup:
                    self._lookup[key] = (대분류명, 중분류명, 대분류코드)

        self._loaded = True

    def 분류(self, dart_sector: str):
        if not self._loaded or not dart_sector or pd.isna(dart_sector):
            return None, dart_sector or "미상"

        key = _clean_text(dart_sector)
        matched = self._lookup.get(key)
        if matched is None:
            return None, dart_sector

        대분류명, 중분류명, 대분류코드 = matched
        대분류명 = _표시명_정리(대분류명)
        세부업종명 = _표시명_정리(중분류명) if 대분류코드 == "C" else 대분류명
        return 대분류명, 세부업종명
