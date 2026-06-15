import pandas as pd
import requests
import zipfile
import io
import os
from pykrx import stock

try:
    from pykiwoom.kiwoom import Kiwoom
except ImportError:
    Kiwoom = None

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

def fetch_kiwoom_data() -> pd.DataFrame:
    """
    Kiwoom OpenAPI+를 통해 종목 정보를 수집합니다.
    (자동 로그인 설정된 32bit 환경)
    """
    if Kiwoom is None:
        print("[OCI/Linux 호환 모드] pykiwoom 모듈이 없으므로 키움 연동을 생략합니다.")
        return pd.DataFrame(columns=["종목코드", "종목명_Kiwoom", "시장_Kiwoom"])

    try:
        kiwoom = Kiwoom()
        kiwoom.CommConnect(block=True)
        
        kospi_codes = kiwoom.GetCodeListByMarket('0')
        kosdaq_codes = kiwoom.GetCodeListByMarket('10')
        
        data = []
        for code in kospi_codes:
            name = kiwoom.GetMasterCodeName(code)
            data.append({"종목코드": code, "종목명_Kiwoom": name, "시장_Kiwoom": "KOSPI"})
            
        for code in kosdaq_codes:
            name = kiwoom.GetMasterCodeName(code)
            data.append({"종목코드": code, "종목명_Kiwoom": name, "시장_Kiwoom": "KOSDAQ"})
            
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Kiwoom OpenAPI 연동 실패 (32bit 환경/로그인 상태 확인): {e}")
        # 오류가 나더라도 전체 파이프라인이 멈추지 않도록 빈 DataFrame 반환
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
