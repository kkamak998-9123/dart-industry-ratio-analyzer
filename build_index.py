# -*- coding: utf-8 -*-
"""상장/비상장(기타법인 포함) 전체 공시법인 검색 인덱스를 SQLite로 생성한다.

인덱스를 RAM이 아니라 디스크(SQLite)에 두는 이유: 전체(약 11.8만 개)를 파이썬
dict로 부모(웹) 프로세스에 상주시키면 +50MB가 늘어, 분석 워커(피크 ~426MB)와
합쳐 512MB를 넘겨 OOM이 재발한다. SQLite는 디스크에서 조회하므로 부모 RAM은
~52MB로 유지되고, 전체 회사(예: 비상장 기타법인 JTBC)도 검색할 수 있다.

무거운 dart_fss corp_list(약 215MB)는 이 스크립트를 1회 별도 프로세스로 실행할
때만 로드되고, 종료 시 회수된다.
"""

import os
import sqlite3
import sys

import dart_fss as dart

from industry import 업종분류기

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "corp_index.db")


def build(db_path: str = DB_PATH) -> int:
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise RuntimeError("DART_API_KEY 환경변수를 설정해주세요.")
    dart.set_api_key(api_key=api_key)

    corp_list = dart.get_corp_list()
    업종분류 = 업종분류기()

    rows = []
    for corp in corp_list.corps:
        d = corp.to_dict()
        name = d.get("corp_name")
        if not name:
            continue
        대분류, 세부업종 = 업종분류.분류(d.get("sector"))
        rows.append((
            d.get("corp_code"), name, d.get("stock_code"),
            대분류, 세부업종,
        ))

    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute(
        "CREATE TABLE corps ("
        "corp_code TEXT PRIMARY KEY, corp_name TEXT, stock_code TEXT, "
        "대분류 TEXT, 세부업종 TEXT)"
    )
    con.executemany("INSERT OR IGNORE INTO corps VALUES (?,?,?,?,?)", rows)
    con.execute("CREATE INDEX idx_name ON corps(corp_name)")
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    return len(rows)


if __name__ == "__main__":
    n = build(sys.argv[1] if len(sys.argv) > 1 else DB_PATH)
    print(f"corp_index.db built: {n} companies (listed + unlisted)")
