import requests         # KRX 서버에 데이터를 요청하기 위한 라이브러리
import pandas as pd     # 받아온 데이터를 표(DataFrame)로 다루기 위한 라이브러리

# KRX 정보데이터시스템(data.krx.co.kr)의 데이터 조회 주소
# (스크린샷의 '주식 기본정보'와 'ETF 기본정보' 화면이 내부적으로 사용하는 주소입니다)
KRX_API_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

# 일반 브라우저처럼 보이게 하는 요청 머리말 (없으면 KRX가 요청을 거부할 수 있음)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",   # 브라우저인 척하는 신분증
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",  # KRX 사이트에서 온 요청인 척
}


def _fetch_krx_table(params: dict) -> pd.DataFrame:
    """
    KRX 데이터 조회 API에 요청을 보내고, 응답 JSON 안의 표 데이터를 DataFrame으로 반환합니다.
    """
    res = requests.post(KRX_API_URL, data=params, headers=KRX_HEADERS, timeout=30)  # 데이터 요청 (30초 제한)
    res.raise_for_status()                                   # 실패(403 등) 시 에러 발생시킴
    payload = res.json()                                     # 응답을 JSON으로 해석

    # KRX 응답은 {"OutBlock_1": [행들...]} 또는 {"output": [행들...]}처럼
    # 표 이름이 조회 종류마다 달라서, "리스트가 들어있는 첫 항목"을 찾는 방식으로 처리합니다
    for value in payload.values():                           # JSON의 각 항목을 확인
        if isinstance(value, list) and value:                # 내용이 있는 리스트(=표 데이터)를 찾으면
            return pd.DataFrame(value)                       # 표로 변환해서 반환

    return pd.DataFrame()                                    # 표 데이터가 없으면 빈 표 반환


def _map_columns(raw: pd.DataFrame, mapping: dict, label: str) -> pd.DataFrame:
    """
    KRX의 영문 항목이름(예: ISU_CD)을 시트에 쓸 한글 열이름(예: 표준코드)으로 바꿉니다.
    KRX가 항목이름을 바꿔서 못 찾는 경우엔 빈 칸으로 두고, 실제 항목이름 목록을 출력해줍니다.
    """
    result = pd.DataFrame()                                  # 결과를 담을 빈 표
    missing = []                                             # 못 찾은 항목을 기록할 리스트

    for krx_key, korean_name in mapping.items():             # (KRX항목이름 -> 한글열이름) 순서대로
        if krx_key in raw.columns:                           # KRX 응답에 그 항목이 있으면
            result[korean_name] = raw[krx_key].astype(str)   # 문자 그대로 가져옴 (숫자 변형 방지)
        else:                                                # 없으면
            result[korean_name] = ""                         # 빈 칸으로 채우고
            missing.append(krx_key)                          # 누락 목록에 기록

    if missing:                                              # 누락된 항목이 있으면 원인 파악용 정보 출력
        print(f"[{label}] 다음 항목을 KRX 응답에서 찾지 못했습니다: {missing}")
        print(f"[{label}] KRX가 실제로 보내온 항목이름들: {list(raw.columns)}")
        print(f"[{label}] 위 목록을 개발자에게 알려주면 이름만 바꿔서 바로 고칠 수 있습니다.")

    return result                                            # 한글 열이름으로 정리된 표 반환


def fetch_stock_basic_info() -> pd.DataFrame:
    """
    KRX '전종목 기본정보(주식)'를 가져옵니다.
    스크린샷 1번(표준코드~상장주식수 12열)과 같은 표를 만듭니다.
    """
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",        # '주식 전종목 기본정보' 화면의 내부 코드 (확인 필요)
        "locale": "ko_KR",                                   # 한국어로 요청
        "mktId": "ALL",                                      # 전체 시장 (KOSPI+KOSDAQ+KONEX)
        "share": "1",                                        # 주식수 단위: 1주
        "csvxls_isNo": "false",                              # 화면조회용 형식으로 요청
    }

    print("[KRX] 주식 전종목 기본정보를 요청합니다...")        # 진행 상황 출력
    raw = _fetch_krx_table(params)                           # KRX에 요청해서 원본 표 받기

    if raw.empty:                                            # 아무것도 못 받았으면
        print("[KRX] 주식 기본정보 응답이 비어있습니다. (로그인 요구 또는 차단 가능성 - 확인 필요)")
        return raw                                           # 빈 표 반환

    # KRX 영문 항목이름 -> 시트 한글 열이름 매핑 (스크린샷 1번과 같은 순서)
    mapping = {
        "ISU_CD": "표준코드",                                 # KR7... 12자리 국제표준코드
        "ISU_NM": "한글 종목명",                              # 정식 종목명
        "ISU_SRT_CD": "단축코드",                             # 6자리 종목코드
        "ISU_ABBRV": "한글 종목약명",                          # 줄임 종목명
        "ISU_ENG_NM": "영문 종목명",                           # 영문 이름
        "LIST_DD": "상장일",                                  # 상장된 날짜
        "MKT_TP_NM": "시장구분",                              # KOSPI / KOSDAQ 등
        "SECUGRP_NM": "증권구분",                             # 주권 / 리츠 등
        "SECT_TP_NM": "소속부",                               # 우량기업부 등 (KOSDAQ만 값 있음)
        "KIND_STKCERT_TP_NM": "주식종류",                      # 보통주 / 우선주
        "PARVAL": "액면가",                                   # 액면가
        "LIST_SHRS": "상장주식수",                             # 상장된 주식 수
    }

    df = _map_columns(raw, mapping, "주식기본정보")            # 한글 열이름 표로 변환
    print(f"[KRX] 주식 기본정보 {len(df)}종목 수신 완료")      # 결과 개수 출력
    return df                                                # 완성된 표 반환


def fetch_etf_basic_info() -> pd.DataFrame:
    """
    KRX '전종목 기본정보(ETF)'를 가져옵니다.
    스크린샷 2번(표준코드~과세유형)과 같은 표를 만듭니다.
    """
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT04601",        # 'ETF 전종목 기본정보' 화면의 내부 코드 (확인 필요)
        "locale": "ko_KR",                                   # 한국어로 요청
        "share": "1",                                        # 좌수 단위: 1좌
        "csvxls_isNo": "false",                              # 화면조회용 형식으로 요청
    }

    print("[KRX] ETF 전종목 기본정보를 요청합니다...")          # 진행 상황 출력
    raw = _fetch_krx_table(params)                           # KRX에 요청해서 원본 표 받기

    if raw.empty:                                            # 아무것도 못 받았으면
        print("[KRX] ETF 기본정보 응답이 비어있습니다. (로그인 요구 또는 차단 가능성 - 확인 필요)")
        return raw                                           # 빈 표 반환

    # KRX 영문 항목이름 -> 시트 한글 열이름 매핑 (스크린샷 2번 순서 / 항목이름은 확인 필요)
    mapping = {
        "ISU_CD": "표준코드",                                 # KR7... 12자리 국제표준코드
        "ISU_SRT_CD": "단축코드",                             # 6자리 종목코드
        "ISU_NM": "한글종목명",                               # 정식 종목명
        "ISU_ABBRV": "한글종목약명",                           # 줄임 종목명
        "ISU_ENG_NM": "영문종목명",                            # 영문 이름
        "LIST_DD": "상장일",                                  # 상장된 날짜
        "ETF_OBJ_IDX_NM": "기초지수명",                        # 따라가는 지수 이름
        "IDX_CALC_INST_NM1": "지수산출기관",                    # 지수를 만드는 기관
        "IDX_CALC_INST_NM2": "추적배수",                       # 일반 / 2X 레버리지 / 1X 인버스 등
        "ETF_REPLICA_METHD_TP_CD": "복제방법",                 # 실물(패시브) / 합성 등
        "IDX_MKT_CLSS_NM": "기초시장분류",                     # 국내 / 해외
        "IDX_ASST_CLSS_NM": "기초자산분류",                    # 주식 / 채권 / 원자재 등
        "LIST_SHRS": "상장좌수",                              # 상장된 좌수
        "COM_ABBRV": "운용사",                                # 자산운용사 이름
        "CU_QTY": "CU수량",                                   # 설정 단위 수량
        "ETF_TOT_FEE": "총보수",                              # 연간 수수료(%)
        "TAX_TP_CD": "과세유형",                              # 과세 방식
    }

    df = _map_columns(raw, mapping, "ETF기본정보")             # 한글 열이름 표로 변환
    print(f"[KRX] ETF 기본정보 {len(df)}종목 수신 완료")        # 결과 개수 출력
    return df                                                # 완성된 표 반환


# 이 파일을 단독 실행하면 KRX 연결 테스트를 합니다 (python3 krx_fetcher.py)
if __name__ == "__main__":
    stock_df = fetch_stock_basic_info()                      # 주식 기본정보 테스트
    print(stock_df.head())                                   # 앞 5줄 미리보기
    etf_df = fetch_etf_basic_info()                          # ETF 기본정보 테스트
    print(etf_df.head())                                     # 앞 5줄 미리보기
