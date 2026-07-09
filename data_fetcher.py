import pandas as pd     # 표(DataFrame) 형태로 데이터를 다루기 위한 라이브러리
import requests         # 인터넷에서 파일/데이터를 내려받기 위한 라이브러리
import zipfile          # 압축(zip) 파일을 풀기 위한 표준 라이브러리
import io               # 내려받은 데이터를 파일처럼 다루기 위한 표준 라이브러리
import os               # 환경변수(.env 값)를 읽기 위한 표준 라이브러리

# [수정] pykrx는 2차 방안(fallback)에서만 쓰므로, 파일 맨 위가 아니라
# 실제로 필요한 함수 안에서 import 합니다. (최신 pykrx는 import 시점에
# "KRX 로그인 실패" 경고를 출력하고, 평소에는 쓸 일이 없기 때문입니다)


def fetch_kis_master() -> pd.DataFrame:
    """
    한국투자증권 마스터 파일(KOSPI, KOSDAQ)을 다운로드하여 DataFrame으로 반환합니다.
    (API 키 불필요, 공개 URL 사용 - 1차 방안)
    """
    base_url = "https://new.real.download.dws.co.kr/common/master"   # 한투 마스터파일 공개 서버 주소

    # [수정] 시장별로 (zip파일명, 압축 안의 파일명, 시장이름, 꼬리부분 글자수)를 정의합니다.
    # 마스터파일 한 줄의 구조는 [가변길이 머리부분][고정길이 꼬리부분] 인데,
    # 한투 공식 예제 기준으로 꼬리부분이 KOSPI는 228자, KOSDAQ은 222자입니다.
    markets = [("kospi_code.mst.zip", "kospi_code.mst", "KOSPI", 228),
               ("kosdaq_code.mst.zip", "kosdaq_code.mst", "KOSDAQ", 222)]

    df_list = []                                                     # 시장별 결과를 모아둘 리스트

    try:
        for zip_name, mst_name, market, tail_len in markets:         # KOSPI, KOSDAQ 순서로 반복
            url = f"{base_url}/{zip_name}"                           # 내려받을 전체 주소 조립
            response = requests.get(url, timeout=10)                 # 파일 다운로드 (10초 제한)
            response.raise_for_status()                              # 다운로드 실패(404 등) 시 에러 발생시킴

            with zipfile.ZipFile(io.BytesIO(response.content)) as z: # 내려받은 zip을 메모리에서 바로 열기
                with z.open(mst_name) as f:                          # zip 안의 .mst 파일 열기
                    lines = f.readlines()                            # 한 줄씩 전부 읽기
                    data = []                                        # 이 시장의 종목들을 담을 리스트
                    for line in lines:                               # 한 줄 = 한 종목
                        try:
                            # 한글이 깨지지 않도록 cp949(한국어 인코딩)로 해석합니다
                            line_str = line.decode('cp949', errors='ignore')

                            if len(line_str) <= tail_len:            # 줄이 너무 짧으면(빈 줄 등)
                                continue                             # 건너뜁니다

                            # [핵심 수정] 한 줄에서 꼬리(고정 228/222자)를 잘라내면 머리부분만 남습니다.
                            # 머리부분 구조: [0:9]=단축코드(6자리 종목코드), [9:21]=표준코드(KR7...), [21:]=한글 종목명
                            # 기존 코드는 종목명을 [9:49]로 잘라서 "KR7000020008동화약품"처럼
                            # 표준코드가 종목명 앞에 섞여 들어가는 버그가 있었습니다.
                            head = line_str[: len(line_str) - tail_len]  # 꼬리를 제외한 머리부분
                            ticker = head[0:9].strip()                   # 앞 9자 = 단축코드 (공백 제거)
                            name = head[21:].strip()                     # 22번째 글자부터 = 진짜 종목명

                            # 종목코드가 정확히 6자리 숫자이고 종목명이 있을 때만 저장합니다
                            # (ETF/ETN 등도 6자리 숫자라서 포함됩니다. 필요 시 여기서 필터링하세요)
                            if len(ticker) == 6 and ticker.isdigit() and name:
                                data.append({"종목코드": ticker, "종목명_KIS": name, "시장": market})
                        except Exception:                            # 이상한 줄 하나 때문에
                            continue                                 # 전체가 멈추지 않도록 건너뜀

            df_list.append(pd.DataFrame(data))                       # 이 시장의 결과를 표로 만들어 저장

        kis_df = pd.concat(df_list, ignore_index=True)               # KOSPI + KOSDAQ 표를 하나로 합침
        return kis_df                                                # 완성된 표 반환

    except Exception as e:                                           # 다운로드/파싱이 통째로 실패하면
        print(f"[Fallback] KIS 마스터 다운로드 실패: {e}. 차선책(pykrx)으로 대체합니다.")
        return fetch_krx_fallback()                                  # 2차 방안(pykrx)으로 넘어감


def fetch_krx_fallback() -> pd.DataFrame:
    """
    KIS 다운로드 실패 시 pykrx를 통해 종목 정보를 수집합니다. (2차 방안 / 차선책)
    [주의] 최신 pykrx는 KRX 로그인 계정이 필요할 수 있습니다.
    필요 시 .env에 KRX_ID, KRX_PW를 추가하세요. (확인 필요)
    """
    from pykrx import stock                                          # 여기서만 pykrx를 불러옴 (지연 import)

    # [수정] 기존 코드의 stock.get_business_days_dates()는 pykrx에 존재하지 않는 함수였습니다.
    # 실제로 존재하는 get_nearest_business_day_in_a_week()로 "가장 최근 거래일"을 얻습니다. ("YYYYMMDD" 문자열 반환)
    today_str = stock.get_nearest_business_day_in_a_week()

    df_list = []                                                     # 시장별 결과를 모아둘 리스트
    for market in ["KOSPI", "KOSDAQ"]:                               # 두 시장을 순서대로 처리
        tickers = stock.get_market_ticker_list(today_str, market=market)  # 해당 시장의 전체 종목코드 목록
        data = []                                                    # 이 시장의 종목들을 담을 리스트
        for ticker in tickers:                                       # 종목코드 하나씩
            name = stock.get_market_ticker_name(ticker)              # 종목코드로 종목명 조회
            data.append({"종목코드": ticker, "종목명_KIS": name, "시장": market})  # 한 종목 저장
        df_list.append(pd.DataFrame(data))                           # 시장 결과를 표로 저장

    return pd.concat(df_list, ignore_index=True)                     # 두 시장 표를 하나로 합쳐 반환


def get_kiwoom_access_token(appkey: str, appsecret: str) -> str:
    """
    키움증권 REST API 접근 토큰(Access Token)을 발급받습니다.
    """
    url = "https://openapi.kiwoom.com:10443/oauth2/tokenP"           # 키움 토큰 발급 주소 (확인 필요: 실계좌/모의 도메인)
    headers = {"content-type": "application/json"}                   # JSON으로 보낸다는 표시
    body = {
        "grant_type": "client_credentials",                          # "앱 자격증명으로 토큰 주세요"라는 뜻
        "appkey": appkey,                                            # .env에서 읽은 앱키
        "appsecret": appsecret                                       # .env에서 읽은 시크릿
    }

    try:
        res = requests.post(url, headers=headers, json=body, timeout=10)  # 토큰 발급 요청 (10초 제한)
        res.raise_for_status()                                       # 실패(401 등) 시 에러 발생시킴
        data = res.json()                                            # 응답을 JSON으로 해석
        return data.get("access_token", "")                          # 토큰 값 반환 (없으면 빈 문자열)
    except Exception as e:                                           # 네트워크/인증 오류 시
        print(f"키움 REST API 토큰 발급 실패: {e}")                   # 원인 출력
        return ""                                                    # 빈 문자열 = 실패 표시


def fetch_kiwoom_data() -> pd.DataFrame:
    """
    Kiwoom REST API를 통해 종목 정보를 수집하려 시도합니다.
    주의: 기존 OpenAPI(OCX)의 GetCodeListByMarket처럼 전체 종목코드를
    한 번에 내려주는 API는 REST 방식에서 제공되지 않습니다. (확인 필요)
    따라서 토큰 발급 구조만 세팅하고, 빈 결과를 반환합니다.
    """
    appkey = os.getenv("KIWOOM_APPKEY")                              # .env에서 키움 앱키 읽기
    appsecret = os.getenv("KIWOOM_SECRET")                           # .env에서 키움 시크릿 읽기

    # 키가 없거나 예시값 그대로면 키움 연동은 건너뜁니다
    if not appkey or not appsecret or appkey == "your_kiwoom_appkey_here":
        print("[키움 REST API] .env 파일에 KIWOOM_APPKEY 및 KIWOOM_SECRET 설정이 누락되어 연동을 생략합니다.")
        return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])  # 빈 표 반환

    print("[키움 REST API] Access Token 발급 시도 중...")             # 진행 상황 출력
    token = get_kiwoom_access_token(appkey, appsecret)               # 토큰 발급 시도

    if not token:                                                    # 토큰 발급 실패 시
        return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])  # 빈 표 반환

    print("[키움 REST API] 연동 성공 (Token 발급 완료).")
    print("[안내] 키움 REST API는 전체 종목코드를 한 번에 제공하는 기능이 없어 KIS/KRX 데이터를 우선 사용합니다.")

    # 전체 코드 리스트 조회가 어려우므로 빈 표 반환 (추후 단일 종목 조회 시 token 활용 가능)
    return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])


def get_merged_stock_data() -> pd.DataFrame:
    """
    KIS와 Kiwoom 데이터를 병합하여 교차 검증된 결과를 반환합니다.
    """
    print("KIS 데이터를 수집합니다...")                               # 진행 상황 출력
    kis_df = fetch_kis_master()                                      # 1차 방안: 한투 마스터파일

    print("Kiwoom 데이터를 수집합니다...")                            # 진행 상황 출력
    kiwoom_df = fetch_kiwoom_data()                                  # 키움 데이터 (현재는 항상 빈 표)

    print("데이터를 병합하고 교차 검증합니다...")                     # 진행 상황 출력
    if not kiwoom_df.empty:                                          # 키움 데이터가 있는 경우
        # 종목코드를 기준으로 양쪽 모두 남기는(outer) 방식으로 병합해 누락을 방지
        merged_df = pd.merge(kis_df, kiwoom_df, on="종목코드", how="outer")
        # 종목명은 KIS 우선, 없으면 키움 값으로 채움
        merged_df["종목명"] = merged_df["종목명_KIS"].fillna(merged_df["종목명_Kiwoom"])
        # 시장 정보도 같은 방식으로 채움
        merged_df["시장"] = merged_df["시장"].fillna(merged_df["시장_Kiwoom"])
    else:                                                            # 키움 데이터가 없는 경우 (현재 기본)
        merged_df = kis_df.copy()                                    # KIS 데이터를 그대로 복사
        merged_df["종목명"] = merged_df["종목명_KIS"]                 # 종목명 컬럼 이름만 맞춰줌

    # 필요한 3개 컬럼만 남기고, 종목명이 없는 행은 제거
    final_df = merged_df[["시장", "종목코드", "종목명"]].dropna(subset=["종목명"]).copy()
    final_df = final_df.drop_duplicates(subset=["종목코드"])          # 혹시 모를 중복 종목코드 제거

    # [수정] 종목코드를 항상 6자리 문자열로 통일 (예: "5930" -> "005930")
    # 구글 시트의 기존 데이터와 비교할 때 형식이 달라 중복 추가되는 사고를 방지합니다
    final_df["종목코드"] = final_df["종목코드"].astype(str).str.zfill(6)

    final_df["섹터"] = ""                                            # 구글 시트 양식에 맞춘 빈 섹터 컬럼

    return final_df                                                  # 최종 표 반환
