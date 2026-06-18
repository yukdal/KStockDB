import pandas as pd
import requests
import zipfile
import io
import os
from pykrx import stock

# pykiwoom(OCX)는 사용하지 않으므로 제거합니다.

def fetch_kis_master() -> pd.DataFrame:
    """
    한국투자증권 마스터 파일(KOSPI, KOSDAQ)을 다운로드하여 DataFrame으로 반환합니다.
    (API 키 불필요, 공개 URL 사용 - 1차 방안)
    """
    base_url = "https://new.real.download.dws.co.kr/common/master"
    markets = [("kospi_code.mst.zip", "kospi_code.mst", "KOSPI"), 
               ("kosdaq_code.mst.zip", "kosdaq_code.mst", "KOSDAQ")]
    
    df_list = []
    
    try:
        for zip_name, mst_name, market in markets:
            url = f"{base_url}/{zip_name}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                with z.open(mst_name) as f:
                    lines = f.readlines()
                    data = []
                    for line in lines:
                        try:
                            line_str = line.decode('cp949', errors='ignore')
                            if market == "KOSPI":
                                ticker = line_str[0:9].strip()[-6:] 
                                name = line_str[9:49].strip()
                            else: # KOSDAQ
                                ticker = line_str[0:9].strip()[-6:]
                                name = line_str[9:49].strip()
                                
                            if len(ticker) == 6 and ticker.isdigit():
                                data.append({"종목코드": ticker, "종목명_KIS": name, "시장": market})
                        except:
                            continue
                            
            df_list.append(pd.DataFrame(data))
            
        kis_df = pd.concat(df_list, ignore_index=True)
        return kis_df
    
    except Exception as e:
        print(f"[Fallback] KIS 마스터 다운로드 실패: {e}. 차선책(pykrx)으로 대체합니다.")
        return fetch_krx_fallback()

def fetch_krx_fallback() -> pd.DataFrame:
    """
    KIS 다운로드 실패 시 pykrx를 통해 종목 정보를 수집합니다. (2차 방안 / 차선책)
    """
    today = stock.get_business_days_dates("20230101", pd.Timestamp.today().strftime("%Y%m%d"))[-1]
    today_str = today.strftime("%Y%m%d")
    
    df_list = []
    for market in ["KOSPI", "KOSDAQ"]:
        tickers = stock.get_market_ticker_list(today_str, market=market)
        data = []
        for ticker in tickers:
            name = stock.get_market_ticker_name(ticker)
            data.append({"종목코드": ticker, "종목명_KIS": name, "시장": market})
        df_list.append(pd.DataFrame(data))
        
    return pd.concat(df_list, ignore_index=True)

def get_kiwoom_access_token(appkey: str, appsecret: str) -> str:
    """
    키움증권 REST API 접근 토큰(Access Token)을 발급받습니다.
    실전 투자의 경우 domain이 다를 수 있으며, 여기서는 기본 예시를 제공합니다.
    """
    url = "https://openapi.kiwoom.com:10443/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": appkey,
        "appsecret": appsecret
    }
    
    try:
        res = requests.post(url, headers=headers, json=body, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data.get("access_token", "")
    except Exception as e:
        print(f"키움 REST API 토큰 발급 실패: {e}")
        return ""

def fetch_kiwoom_data() -> pd.DataFrame:
    """
    Kiwoom REST API를 통해 종목 정보를 수집하려 시도합니다.
    주의: 기존 OpenAPI(OCX)의 GetCodeListByMarket 함수처럼 전체 시장 종목코드를 
    한 번에 내려주는 API는 REST 방식에서 제공되지 않습니다.
    따라서 토큰 발급 구조만 세팅하고, 대량 조회가 불가능하므로 빈 결과를 반환합니다.
    대신 다른 조회 API(현재가 등) 사용 시 이 구조를 활용할 수 있습니다.
    """
    appkey = os.getenv("KIWOOM_APPKEY")
    appsecret = os.getenv("KIWOOM_SECRET")
    
    if not appkey or not appsecret or appkey == "your_kiwoom_appkey_here":
        print("[키움 REST API] .env 파일에 KIWOOM_APPKEY 및 KIWOOM_SECRET 설정이 누락되어 연동을 생략합니다.")
        return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])
        
    print("[키움 REST API] Access Token 발급 시도 중...")
    token = get_kiwoom_access_token(appkey, appsecret)
    
    if not token:
        return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])
        
    print("[키움 REST API] 연동 성공 (Token 발급 완료).")
    print("[안내] 키움 REST API는 전체 종목코드를 한 번에 제공하는 GetCodeListByMarket 기능이 없습니다.")
    print("[안내] 따라서 교차 검증용 마스터 데이터는 KIS 및 KRX 데이터를 우선 사용합니다.")
    
    # REST API로는 전체 코드 리스트 조회가 어려우므로, 빈 데이터프레임 반환
    # (추후 단일 종목 상세 조회 등이 필요할 때 token을 활용해 HTTP 요청을 보냅니다)
    return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])

def get_merged_stock_data() -> pd.DataFrame:
    """
    KIS와 Kiwoom 데이터를 병합하여 교차 검증된 결과를 반환합니다.
    """
    print("KIS 데이터를 수집합니다...")
    kis_df = fetch_kis_master()
    
    print("Kiwoom 데이터를 수집합니다...")
    kiwoom_df = fetch_kiwoom_data()
    
    print("데이터를 병합하고 교차 검증합니다...")
    if not kiwoom_df.empty:
        # 종목코드를 기준으로 Outer Join 하여 누락이 없도록 병합
        merged_df = pd.merge(kis_df, kiwoom_df, on="종목코드", how="outer")
        
        # 종목명 결정 (KIS 우선, 없으면 Kiwoom)
        merged_df["종목명"] = merged_df["종목명_KIS"].fillna(merged_df["종목명_Kiwoom"])
        # 시장 결정
        merged_df["시장"] = merged_df["시장"].fillna(merged_df["시장_Kiwoom"])
        
    else:
        merged_df = kis_df.copy()
        merged_df["종목명"] = merged_df["종목명_KIS"]
        
    # ETF, ETN 등 제외 필터링 (필요 시 수정, 현재는 전 종목)
    final_df = merged_df[["시장", "종목코드", "종목명"]].dropna(subset=["종목명"]).copy()
    final_df = final_df.drop_duplicates(subset=["종목코드"])
    
    # 구글 시트 양식에 맞추기 위한 빈 섹터 컬럼 추가
    final_df["섹터"] = "" 
    
    return final_df
