import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

def update_google_sheet(df: pd.DataFrame):
    """
    수집된 종목 데이터프레임을 Google Sheet와 동기화합니다.
    신규 추가(Append) 및 기존 종목명 변경(Update)을 수행합니다.
    """
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    
    if not spreadsheet_id or not os.path.exists(json_path):
        print(f"Google Sheets 설정 누락 또는 JSON 키 파일을 찾을 수 없습니다. (경로: {json_path})")
        return
        
    print("구글 시트에 연결합니다...")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
    client = gspread.authorize(creds)
    
    # 탭 이름은 [종목코드모음]
    sheet = client.open_by_key(spreadsheet_id).worksheet("종목코드모음")
    
    # 기존 데이터 로드
    existing_data = sheet.get_all_records()
    existing_df = pd.DataFrame(existing_data)
    
    # 시트가 비어있을 경우 헤더 초기화 및 전체 입력
    if existing_df.empty:
        print("시트가 비어있습니다. 초기 데이터를 씁니다.")
        headers = ["시장", "종목코드", "종목명", "섹터"]
        sheet.append_row(headers)
        new_values = df[headers].values.tolist()
        sheet.append_rows(new_values)
        print(f"초기화 완료: {len(new_values)} 종목 추가")
        return

    # 종목코드를 문자열로 (앞에 0이 유지되도록)
    existing_df['종목코드'] = existing_df['종목코드'].astype(str).str.zfill(6)
    existing_codes = set(existing_df['종목코드'].tolist())
    
    # 1. 신규 종목 찾기
    new_stocks = df[~df['종목코드'].isin(existing_codes)]
    if not new_stocks.empty:
        print(f"신규 종목 {len(new_stocks)}개 발견! 시트 맨 아래에 추가합니다.")
        headers = ["시장", "종목코드", "종목명", "섹터"]
        new_values = new_stocks[headers].values.tolist()
        sheet.append_rows(new_values)
    else:
        print("추가할 신규 종목이 없습니다.")
        
    # 2. 종목명 변경된 기존 종목 찾기 및 덮어쓰기 (Update)
    cells_to_update = []
    
    # 종목코드 -> 행 번호 매핑 (헤더 1행, 1-indexed 보정 = 인덱스 + 2)
    code_to_row = {code: idx + 2 for idx, code in enumerate(existing_df['종목코드'])}
    
    for _, row in df.iterrows():
        code = row['종목코드']
        if code in existing_codes:
            old_name = str(existing_df[existing_df['종목코드'] == code]['종목명'].values[0])
            new_name = str(row['종목명'])
            
            if old_name != new_name:
                row_idx = code_to_row[code]
                print(f"종목명 변경 감지: {code} ({old_name} -> {new_name})")
                # 종목명은 C열 (3번째 열)
                cells_to_update.append(gspread.models.Cell(row_idx, 3, new_name))
                
    if cells_to_update:
        print(f"총 {len(cells_to_update)}건의 변경사항을 일괄 업데이트(Overwrite)합니다.")
        sheet.update_cells(cells_to_update)
    else:
        print("종목명/섹터가 변경된 항목이 없습니다.")

    print("구글 시트 동기화가 성공적으로 완료되었습니다.")
