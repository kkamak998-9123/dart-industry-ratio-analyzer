"""공용 유틸: 재무제표 컬럼(연도/연결여부) 파싱"""


def 연도_라벨(col) -> str:
    """dart_fss가 반환하는 컬럼 라벨에서 연도(앞 4자리)를 뽑아낸다.

    컬럼은 'label_ko' 같은 단순 문자열이거나, 재무제표에 연결/별도 등
    보고서 종류가 함께 존재할 때 ('20181231', ('연결재무제표',)) 같은
    튜플 형태로 들어온다. 둘 다 지원한다.
    """
    date_part = col[0] if isinstance(col, tuple) else col
    return str(date_part)[:4]


def 연결여부(col) -> bool:
    """컬럼 라벨의 보고서 구분에 '연결'이 포함되는지 여부"""
    if not isinstance(col, tuple) or len(col) < 2:
        return False
    구분 = col[1]
    if isinstance(구분, tuple):
        구분 = 구분[0] if 구분 else ""
    return "연결" in str(구분)
