import os               # 환경변수(.env의 KRX_AUTH_KEY)를 읽기 위한 표준 라이브러리
import datetime         # 기준일자 계산용 표준 라이브러리
import requests         # KRX 서버에 데이터를 요청하기 위한 라이브러리
import pandas as pd     # 받아온 데이터를 표(DataFrame)로 다루기 위한 라이브러리
import exchange_calendars as xcals   # 한국거래소 거래일 달력 (기준일자 계산에 사용)

# ============================================================
# [1순위] KRX Open API (공식 허가 통로, 인증키 필요)
# ============================================================
# .env에 KRX_AUTH_KEY가 있으면 이 공식 API를 먼저 사용합니다.
# [수정] http -> https : http로 보내면 KRX가 https로 이동시키는 과정에서
# 인증키 머리말이 소실되어 401(인증 거부)이 날 수 있습니다.
KRX_OPENAPI_BASE = "https://data-dbg.krx.co.kr/svc/apis"   # KRX Open API 기본 주소 (확인 필요)

# ============================================================
# [2순위] KRX 정보데이터시스템 웹 조회 (인증키 없거나 실패 시 대체)
# ============================================================
# [수정] 웹 조회도 전부 https로 변경 (http 요청은 400으로 거절됨)
KRX_WEB_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"   # 웹 화면용 데이터 주소
KRX_WEB_PAGE_URL = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"  # 실제 화면 페이지 주소
KRX_WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",   # 브라우저인 척하는 신분증
}

# 한국거래소 달력을 한 번만 로드해서 재사용
_krx_calendar = xcals.get_calendar("XKRX")


def _recent_trading_days(count: int = 3) -> list:
    """
    최근 거래일 여러 개를 "YYYYMMDD" 문자열 목록으로 반환합니다. (최신 날짜부터)
    KRX는 '오늘' 데이터를 장 마감 정산 후에야 제공하는 경우가 많아서,
    오늘 -> 직전 거래일 -> 그 전 거래일 순으로 재시도할 수 있도록 여러 날짜를 준비합니다.
    """
    day = pd.Timestamp(datetime.date.today())                # 오늘 날짜부터 시작
    if not _krx_calendar.is_session(day):                    # 오늘이 휴장일이면
        day = _krx_calendar.previous_session(day)            # 가장 최근 거래일로 이동

    days = [day.strftime("%Y%m%d")]                          # 첫 번째 후보 날짜 저장
    for _ in range(count - 1):                               # 필요한 개수만큼
        day = _krx_calendar.previous_session(day)            # 하루씩 과거 거래일로 이동
        days.append(day.strftime("%Y%m%d"))                  # 후보 목록에 추가
    return days                                              # 예: ['20260709', '20260708', '20260707']


def _json_to_df(payload: dict) -> pd.DataFrame:
    """응답 JSON 안에서 표 데이터(리스트)를 찾아 DataFrame으로 반환합니다."""
    for value in payload.values():                           # JSON의 각 항목을 확인
        if isinstance(value, list) and value:                # 내용이 있는 리스트(=표 데이터)를 찾으면
            return pd.DataFrame(value)                       # 표로 변환해서 반환
    return pd.DataFrame()                                    # 표 데이터가 없으면 빈 표


def _fetch_openapi(path: str, params: dict) -> pd.DataFrame:
    """
    KRX Open API(공식)에 인증키를 담아 요청하고 결과를 표로 반환합니다.
    """
    auth_key = os.getenv("KRX_AUTH_KEY", "")                 # .env에서 인증키 읽기
    headers = {"AUTH_KEY": auth_key}                         # KRX Open API는 AUTH_KEY 머리말로 인증 (확인 필요)
    url = f"{KRX_OPENAPI_BASE}/{path}"                       # 전체 주소 조립
    res = requests.get(url, params=params, headers=headers, timeout=30)  # 데이터 요청 (30초 제한)
    res.raise_for_status()                                   # 실패(401/403 등) 시 에러 발생시킴
    return _json_to_df(res.json())                           # 표로 변환해서 반환


def _fetch_web(params: dict, menu_id: str) -> pd.DataFrame:
    """
    KRX 정보데이터시스템 웹 조회(비공식)로 데이터를 받아 표로 반환합니다. (대체 수단)
    [수정] 브라우저처럼 행동: 먼저 실제 화면 페이지를 방문해 쿠키를 받은 뒤,
    그 페이지에서 조회한 것처럼 데이터를 요청합니다. (바로 요청하면 400으로 거절됨)
    """
    session = requests.Session()                             # 쿠키를 기억하는 연결 세션 생성
    session.headers.update(KRX_WEB_HEADERS)                  # 브라우저인 척하는 머리말 적용

    page_url = f"{KRX_WEB_PAGE_URL}?menuId={menu_id}"        # 실제 통계 화면 페이지 주소
    session.get(page_url, timeout=30)                        # 1단계: 화면 페이지 방문 (쿠키 획득)

    # 2단계: 방금 그 화면에서 조회 버튼을 누른 것처럼 데이터 요청
    res = session.post(KRX_WEB_URL, data=params, headers={"Referer": page_url}, timeout=30)
    res.raise_for_status()                                   # 실패 시 에러 발생시킴
    return _json_to_df(res.json())                           # 표로 변환해서 반환


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


# KRX 영문 항목이름 -> 시트 한글 열이름 매핑 (주식 기본정보 12열, 스크린샷 1과 같은 순서)
STOCK_MAPPING = {
    "ISU_CD": "표준코드",                                     # KR7... 12자리 국제표준코드
    "ISU_NM": "한글 종목명",                                  # 정식 종목명
    "ISU_SRT_CD": "단축코드",                                 # 6자리 종목코드
    "ISU_ABBRV": "한글 종목약명",                              # 줄임 종목명
    "ISU_ENG_NM": "영문 종목명",                               # 영문 이름
    "LIST_DD": "상장일",                                      # 상장된 날짜
    "MKT_TP_NM": "시장구분",                                  # KOSPI / KOSDAQ 등
    "SECUGRP_NM": "증권구분",                                 # 주권 / 리츠 등
    "SECT_TP_NM": "소속부",                                   # 우량기업부 등 (KOSDAQ만 값 있음)
    "KIND_STKCERT_TP_NM": "주식종류",                          # 보통주 / 우선주
    "PARVAL": "액면가",                                       # 액면가
    "LIST_SHRS": "상장주식수",                                 # 상장된 주식 수
}

# KRX 영문 항목이름 -> 시트 한글 열이름 매핑 (ETF 기본정보, 스크린샷 2 순서 / 항목이름은 확인 필요)
ETF_MAPPING = {
    "ISU_CD": "표준코드",                                     # KR7... 12자리 국제표준코드
    "ISU_SRT_CD": "단축코드",                                 # 6자리 종목코드
    "ISU_NM": "한글종목명",                                   # 정식 종목명
    "ISU_ABBRV": "한글종목약명",                               # 줄임 종목명
    "ISU_ENG_NM": "영문종목명",                                # 영문 이름
    "LIST_DD": "상장일",                                      # 상장된 날짜
    "ETF_OBJ_IDX_NM": "기초지수명",                            # 따라가는 지수 이름
    "IDX_CALC_INST_NM1": "지수산출기관",                        # 지수를 만드는 기관
    "IDX_CALC_INST_NM2": "추적배수",                           # 일반 / 2X 레버리지 / 1X 인버스 등
    "ETF_REPLICA_METHD_TP_CD": "복제방법",                     # 실물(패시브) / 합성 등
    "IDX_MKT_CLSS_NM": "기초시장분류",                         # 국내 / 해외
    "IDX_ASST_CLSS_NM": "기초자산분류",                        # 주식 / 채권 / 원자재 등
    "LIST_SHRS": "상장좌수",                                  # 상장된 좌수
    "COM_ABBRV": "운용사",                                    # 자산운용사 이름
    "CU_QTY": "CU수량",                                       # 설정 단위 수량
    "ETF_TOT_FEE": "총보수",                                  # 연간 수수료(%)
    "TAX_TP_CD": "과세유형",                                  # 과세 방식
}


def _fetch_stock_via_openapi() -> pd.DataFrame:
    """
    [1순위] KRX Open API로 유가증권/코스닥/코넥스 종목 기본정보를 받아 합칩니다.
    오늘 데이터가 아직 없으면(장 마감 전) 직전 거래일로 자동 재시도합니다.
    """
    # 시장별 API 경로와 시장 이름 (Open API는 시장마다 주소가 다름 - 확인 필요)
    endpoints = [("sto/stk_isu_base_info", "KOSPI"),         # 유가증권 종목기본정보
                 ("sto/ksq_isu_base_info", "KOSDAQ"),        # 코스닥 종목기본정보
                 ("sto/knx_isu_base_info", "KONEX")]         # 코넥스 종목기본정보

    for base_date in _recent_trading_days(3):                # 오늘 -> 직전 -> 그 전 거래일 순서로 시도
        df_list = []                                         # 시장별 결과를 모아둘 리스트
        for path, market in endpoints:                       # 세 시장을 순서대로 요청
            raw = _fetch_openapi(path, {"basDd": base_date}) # 기준일자를 넣어 요청
            if raw.empty:                                    # 이 시장 응답이 비었으면
                continue                                     # 다음 시장으로
            if "MKT_TP_NM" not in raw.columns:               # 응답에 시장구분 항목이 없으면
                raw["MKT_TP_NM"] = market                    # 우리가 아는 시장 이름으로 채움
            df_list.append(raw)                              # 결과 모음에 추가

        if df_list:                                          # 이 날짜로 데이터를 받았으면
            print(f"[KRX OpenAPI] 기준일 {base_date} 데이터 수신 성공")
            return pd.concat(df_list, ignore_index=True)     # 시장별 표를 하나로 합쳐 반환

        # 이 날짜는 세 시장 모두 비어있음 -> 아직 정산 전일 수 있으니 하루 전으로 재시도
        print(f"[KRX OpenAPI] 기준일 {base_date} 데이터가 아직 없습니다. 직전 거래일로 재시도합니다...")

    return pd.DataFrame()                                    # 모든 날짜 실패 시 빈 표 (웹 방식으로 전환)


def fetch_stock_basic_info() -> pd.DataFrame:
    """
    KRX '전종목 기본정보(주식)'를 가져옵니다. (스크린샷 1번과 같은 12열 표)
    인증키가 있으면 공식 Open API를 먼저 쓰고, 없거나 실패하면 웹 조회로 대체합니다.
    """
    raw = pd.DataFrame()                                     # 원본 데이터를 담을 빈 표

    if os.getenv("KRX_AUTH_KEY"):                            # .env에 인증키가 있으면
        print("[KRX] 공식 Open API(인증키)로 주식 기본정보를 요청합니다...")
        try:
            raw = _fetch_stock_via_openapi()                 # 1순위: 공식 API 시도
        except Exception as e:                               # 주소/인증 문제 등으로 실패하면
            print(f"[KRX] Open API 요청 실패: {e}")           # 원인 출력 후
            raw = pd.DataFrame()                             # 빈 표로 두고 웹 방식으로 전환

    if raw.empty:                                            # 인증키가 없거나 Open API가 실패했으면
        print("[KRX] 웹 조회 방식으로 주식 기본정보를 요청합니다...")
        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",    # '주식 전종목 기본정보' 화면 내부 코드 (확인 필요)
            "locale": "ko_KR", "mktId": "ALL",               # 한국어 / 전체 시장
            "share": "1", "csvxls_isNo": "false",            # 1주 단위 / 화면조회 형식
        }
        try:
            # MDC0201020101 = '전종목 기본정보(주식)' 화면의 메뉴 번호 (확인 필요)
            raw = _fetch_web(params, menu_id="MDC0201020101")  # 2순위: 웹 조회
        except Exception as e:                               # 웹 조회마저 실패해도 크래시 대신 안내
            print(f"[KRX] 웹 조회 실패: {e}")
            raw = pd.DataFrame()                             # 빈 표로 정리

    if raw.empty:                                            # 두 방식 모두 실패하면
        print("[KRX] 주식 기본정보를 받지 못했습니다. (네트워크/인증키/차단 여부 확인 필요)")
        return raw                                           # 빈 표 반환

    df = _map_columns(raw, STOCK_MAPPING, "주식기본정보")     # 한글 열이름 표로 변환
    print(f"[KRX] 주식 기본정보 {len(df)}종목 수신 완료")      # 결과 개수 출력
    return df                                                # 완성된 표 반환


# 'ETF 일별매매정보' API의 영문 항목이름 -> 한글 열이름 매핑
# [참고] KRX Open API에는 ETF '기본정보' API가 없어서(확인 필요) 일별매매정보로 대체합니다.
# 따라서 운용사/총보수/CU수량/과세유형 등은 이 방식으로는 받을 수 없습니다.
ETF_TRD_MAPPING = {
    "ISU_CD": "단축코드",                                     # 6자리 종목코드
    "ISU_NM": "한글종목명",                                   # 종목명
    "IDX_IND_NM": "기초지수명",                                # 따라가는 지수 이름
    "TDD_CLSPRC": "종가",                                     # 해당일 마감 가격
    "NAV": "NAV",                                            # 순자산가치 (ETF의 실제 가치)
    "LIST_SHRS": "상장좌수",                                  # 상장된 좌수
    "MKTCAP": "시가총액",                                     # 시장 가격 기준 총액
    "INVSTASST_NETASST_TOTAMT": "순자산총액",                  # 운용 자산 총액
    "BAS_DD": "기준일",                                       # 데이터 기준 날짜
}


def _fetch_etf_via_openapi() -> pd.DataFrame:
    """
    [1순위] KRX Open API의 'ETF 일별매매정보'(etp/etf_bydd_trd)로 ETF 목록을 받아옵니다.
    오늘 데이터가 아직 없으면 직전 거래일로 자동 재시도합니다.
    """
    for base_date in _recent_trading_days(3):                # 오늘 -> 직전 -> 그 전 거래일 순서로 시도
        raw = _fetch_openapi("etp/etf_bydd_trd", {"basDd": base_date})  # ETF 일별매매정보 요청
        if not raw.empty:                                    # 데이터를 받았으면
            print(f"[KRX OpenAPI] ETF 기준일 {base_date} 데이터 수신 성공")
            return raw                                       # 그대로 반환
        print(f"[KRX OpenAPI] ETF 기준일 {base_date} 데이터가 아직 없습니다. 직전 거래일로 재시도합니다...")
    return pd.DataFrame()                                    # 모든 날짜 실패 시 빈 표 (웹 방식으로 전환)


def fetch_etf_basic_info() -> pd.DataFrame:
    """
    KRX '전종목 기본정보(ETF)'를 가져옵니다. (스크린샷 2번과 같은 표)
    인증키가 있으면 공식 Open API를 먼저 쓰고, 없거나 실패하면 웹 조회로 대체합니다.
    """
    raw = pd.DataFrame()                                     # 원본 데이터를 담을 빈 표
    mapping = ETF_MAPPING                                    # 기본은 웹 조회용 매핑
    label = "ETF기본정보"                                     # 안내 메시지용 이름

    if os.getenv("KRX_AUTH_KEY"):                            # .env에 인증키가 있으면
        print("[KRX] 공식 Open API(인증키)로 ETF 정보를 요청합니다...")
        try:
            raw = _fetch_etf_via_openapi()                   # 1순위: 공식 API(일별매매정보) 시도
            if not raw.empty:                                # 성공했으면
                mapping = ETF_TRD_MAPPING                    # 일별매매정보용 매핑 사용
                label = "ETF일별정보"                         # 안내 이름도 변경
        except Exception as e:                               # 주소/인증 문제 등
            print(f"[KRX] ETF Open API 요청 실패: {e}")
            print("[KRX] KRX Open API 사이트에서 'ETF 일별매매정보' API의 이용신청 여부를 확인해주세요. (확인 필요)")
            raw = pd.DataFrame()                             # 빈 표로 두고 웹 방식으로 전환

    if raw.empty:                                            # 인증키가 없거나 Open API가 실패했으면
        print("[KRX] 웹 조회 방식으로 ETF 기본정보를 요청합니다...")
        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT04601",    # 'ETF 전종목 기본정보' 화면 내부 코드 (확인 필요)
            "locale": "ko_KR",                               # 한국어로 요청
            "share": "1", "csvxls_isNo": "false",            # 1좌 단위 / 화면조회 형식
        }
        try:
            # MDC0201040103 = '전종목 기본정보(ETF)' 화면의 메뉴 번호 (확인 필요)
            raw = _fetch_web(params, menu_id="MDC0201040103")  # 2순위: 웹 조회
        except Exception as e:                               # 실패해도 크래시 대신 안내
            print(f"[KRX] ETF 웹 조회 실패: {e}")
            raw = pd.DataFrame()                             # 빈 표로 정리

    if raw.empty:                                            # 두 방식 모두 실패하면
        print("[KRX] ETF 정보를 받지 못했습니다. (Open API 이용신청 항목/주소 확인 필요)")
        return raw                                           # 빈 표 반환

    df = _map_columns(raw, mapping, label)                   # 출처에 맞는 매핑으로 한글 열이름 표 변환
    print(f"[KRX] {label} {len(df)}종목 수신 완료")           # 결과 개수 출력
    return df                                                # 완성된 표 반환


# 이 파일을 단독 실행하면 KRX 연결 테스트를 합니다 (python3 krx_fetcher.py)
if __name__ == "__main__":
    from dotenv import load_dotenv                           # .env 읽기용
    load_dotenv()                                            # KRX_AUTH_KEY 등 환경변수 로드

    key = os.getenv("KRX_AUTH_KEY")                          # 인증키 확인
    print(f"KRX_AUTH_KEY 설정 여부: {'설정됨 (' + key[:4] + '****)' if key else '없음 - 웹 조회만 사용'}")

    stock_df = fetch_stock_basic_info()                      # 주식 기본정보 테스트
    print(stock_df.head())                                   # 앞 5줄 미리보기
    etf_df = fetch_etf_basic_info()                          # ETF 기본정보 테스트
    print(etf_df.head())                                     # 앞 5줄 미리보기
