# -*- coding: utf-8 -*-
"""재무제표 추출 워커 — 분석 요청마다 별도 프로세스로 1회 실행되고 종료된다.

corp_list(215MB)를 상주시키는 부모(웹) 프로세스와 달리, 이 워커는 corp_code
문자열만으로 dart_fss 추출을 수행한다. 종료 시 OS가 메모리를 완전히 회수하므로
연속 조회에도 부모 프로세스에 메모리가 누적(creep)되지 않는다.

사용법:  python analyze_worker.py <corp_code> <출력파일경로>
출력:    <출력파일>에 JSON {"statements": {...}}  또는  {"error": "..."}
         (dart_fss가 진행바를 stdout/stderr에 찍으므로 결과는 파일로 전달)
"""

import json
import sys

import dart_service


def analyze(corp_code: str) -> dict:
    try:
        원본재무제표 = dart_service.재무제표추출(corp_code)
    except Exception as e:  # noqa: BLE001
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
    return {"statements": statements}


def main() -> None:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: analyze_worker.py <corp_code> <out_path>\n")
        sys.exit(2)
    corp_code, out_path = sys.argv[1], sys.argv[2]
    result = analyze(corp_code)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
