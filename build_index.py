# -*- coding: utf-8 -*-
"""상장사 검색/업종 인덱스를 1회 생성해 data/corp_index.json 으로 저장한다.

무거운 dart_fss corp_list(약 215MB)를 부모(웹) 프로세스에 상주시키지 않기 위해,
이 스크립트를 별도 프로세스로 1회만 실행해 가벼운 JSON 인덱스를 만든다.
인덱스에는 회사별 대분류/세부업종까지 미리 계산해 담으므로, 런타임에는
dart_fss·pandas 없이도 검색·업종표시·추천비율 산출이 가능하다.
"""

import json
import os
import sys

import dart_fss as dart

from industry import 업종분류기

INDEX_PATH = os.path.join(os.path.dirname(__file__), "data", "corp_index.json")


def build(output_path: str = INDEX_PATH) -> int:
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise RuntimeError("DART_API_KEY 환경변수를 설정해주세요.")
    dart.set_api_key(api_key=api_key)

    corp_list = dart.get_corp_list()
    업종분류 = 업종분류기()

    records = []
    for corp in corp_list.corps:
        d = corp.to_dict()
        stock_code = d.get("stock_code")
        if not stock_code:  # 상장사만
            continue
        대분류, 세부업종 = 업종분류.분류(d.get("sector"))
        records.append({
            "corp_code": d.get("corp_code"),
            "corp_name": d.get("corp_name"),
            "stock_code": stock_code,
            "대분류": 대분류,
            "세부업종": 세부업종,
        })

    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    os.replace(tmp, output_path)
    return len(records)


if __name__ == "__main__":
    n = build(sys.argv[1] if len(sys.argv) > 1 else INDEX_PATH)
    print(f"corp_index built: {n} listed companies")
