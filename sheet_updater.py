import gspread          # 구글 스프레드시트를 파이썬에서 조작하는 라이브러리
import pandas as pd     # 표(DataFrame) 형태로 데이터를 다루기 위한 라이브러리
import os               # 환경변수(.env 값)와 파일 존재 확인용 표준 라이브러리
from dotenv import load_dotenv   # .env 파일의 값을 환경변수로 읽어들이는 라이브러리

load_dotenv()           # 이 파일이 import될 때 .env 내용을 환경변수로 로드


def update_google_sheet(df: pd.DataFrame):
    """
    수집된 종목 데이터프레임을 Google Sheet와 동기화합니다.
    신규 추가(Append) 및 기존 종목명 변경(Update)을 수행합니다.
    """
    spreadsheet_id = os.getenv("SPREADSHEET_ID")                     # .env에서 시트 ID 읽기
    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")  # 인증 키 파일 경로 (기본값 있음)

    # 시트 ID가 없거나 키 파일이 없으면 진행 불가이므로 안내 후 종료
    if not spreadsheet_id or not os.path.exists(json_path):
        print(f"Google Sheets 설정 누락 또는 JSON 키 파일을 찾을 수 없습니다. (경로: {json_path})")
        return

    print("구글 시트에 연결합니다...")                                # 진행 상황 출력
    try:
        client = gspread.service_account(filename=json_path)         # 서비스 계정으로 구글 인증
    except Exception as e:                                           # 키 파일이 잘못된 경우 등
        print(f"구글 인증 실패. service_account.json 파일을 확인하세요: {e}")
        return

    # [수정] 자동 관리 전용 탭 이름 (.env에 WORKSHEET_NAME을 넣으면 바꿀 수 있고, 기본값은 "한국종목코드_자동")
    # 기존 "한국종목코드" 탭(KRX 12열 양식)은 건드리지 않고, 프로그램 전용 탭을 따로 사용합니다
    worksheet_name = os.getenv("WORKSHEET_NAME", "한국종목코드_자동")

    # 스프레드시트 파일 자체를 열기
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except Exception as e:                                           # 시트 ID 오류, 권한 미부여 등
        print(f"스프레드시트를 열 수 없습니다. 시트 ID와 서비스 계정 편집자 권한 부여 여부를 확인하세요: {e}")
        return

    # [수정] 전용 탭이 있으면 열고, 없으면 자동으로 새로 만듭니다 (첫 실행 시 수동 작업 불필요)
    try:
        sheet = spreadsheet.worksheet(worksheet_name)                # 탭 열기 시도
    except gspread.WorksheetNotFound:                                # 탭이 아직 없으면
        print(f"'{worksheet_name}' 탭이 없어서 새로 만듭니다.")
        sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=10)  # 새 탭 생성

    # 기존 데이터 전체를 2차원 리스트로 읽어옴 (헤더 중복이 있어도 에러가 안 나는 방식)
    existing_data = sheet.get_all_values()

    headers = ["시장", "종목코드", "종목명", "섹터"]                  # 프로그램이 사용하는 열 제목

    # [수정] "초기화가 필요한 상태"인지 판단합니다.
    # 완전히 빈 탭은 보통 빈 목록([])이 오지만, gspread 버전에 따라
    # 빈 행 하나([[''])를 돌려주는 경우가 있어서 KeyError: '종목코드'가 났습니다.
    # 그래서 목록이 비었는지가 아니라, 1행(제목 줄)에 '종목코드'가 있는지로 판단합니다.
    if not existing_data or "종목코드" not in existing_data[0]:
        # 제목 줄은 없는데 다른 내용이 들어있는 탭이라면, 덮어쓰면 위험하므로 중단
        has_content = any(any(str(cell).strip() for cell in row) for row in existing_data)
        if has_content:
            print(f"'{worksheet_name}' 탭에 알 수 없는 양식의 데이터가 있어 안전을 위해 중단합니다. "
                  f"(1행에 '{headers}' 제목 줄이 필요합니다)")
            return

        print("시트가 비어있습니다. 초기 데이터를 씁니다.")
        # 헤더 1줄 + 전체 종목을 A1 셀부터 한 번의 요청으로 기록합니다
        all_values = [headers] + df[headers].values.tolist()
        # value_input_option="RAW" : "005930" 같은 값을 숫자로 바꾸지 않고 문자 그대로 저장 (앞의 0 보존)
        sheet.update(range_name="A1", values=all_values, value_input_option="RAW")
        print(f"초기화 완료: {len(all_values) - 1} 종목 추가")
        return

    # 시트에 데이터가 있는 경우: 표(DataFrame)로 변환해서 비교 준비
    headers_in_sheet = existing_data[0]                              # 첫 줄 = 열 제목
    existing_df = pd.DataFrame(existing_data[1:], columns=headers_in_sheet)  # 나머지 = 데이터

    # 종목코드를 6자리 문자열로 통일 (시트에서 "5930"으로 읽혀도 "005930"으로 맞춤)
    existing_df['종목코드'] = existing_df['종목코드'].astype(str).str.zfill(6)
    existing_codes = set(existing_df['종목코드'].tolist())            # 빠른 검색을 위해 집합(set)으로 변환

    # 1. 신규 종목 찾기: 새 데이터 중 시트에 없는 종목코드만 골라냄
    new_stocks = df[~df['종목코드'].isin(existing_codes)]
    if not new_stocks.empty:                                         # 신규 종목이 있으면
        print(f"신규 종목 {len(new_stocks)}개 발견! 시트 맨 아래에 추가합니다.")
        headers = ["시장", "종목코드", "종목명", "섹터"]              # 시트 열 순서에 맞춤
        new_values = new_stocks[headers].values.tolist()             # 2차원 리스트로 변환
        sheet.append_rows(new_values, value_input_option="RAW")      # 맨 아래에 일괄 추가 (앞의 0 보존)
    else:
        print("추가할 신규 종목이 없습니다.")

    # 2. 종목명이 변경된 기존 종목 찾기 및 덮어쓰기 (Update)
    cells_to_update = []                                             # 수정할 셀들을 모아둘 리스트

    # 종목코드 -> 시트 행 번호 매핑 (헤더가 1행이므로: 인덱스 + 2 = 실제 행 번호)
    code_to_row = {code: idx + 2 for idx, code in enumerate(existing_df['종목코드'])}
    # [수정] 종목코드 -> 기존 종목명 매핑을 미리 만들어둠
    # (기존 코드는 종목마다 표 전체를 다시 검색해서 2,700종목 기준 수백만 번 비교하는 비효율이 있었습니다)
    code_to_old_name = dict(zip(existing_df['종목코드'], existing_df['종목명']))

    for _, row in df.iterrows():                                     # 새 데이터를 한 종목씩 확인
        code = row['종목코드']                                       # 이 종목의 코드
        if code in existing_codes:                                   # 시트에 이미 있는 종목이면
            old_name = str(code_to_old_name[code])                   # 시트에 저장된 기존 종목명
            new_name = str(row['종목명'])                            # 이번에 수집한 최신 종목명

            if old_name != new_name:                                 # 이름이 달라졌으면 (사명 변경 등)
                row_idx = code_to_row[code]                          # 시트에서 이 종목이 있는 행 번호
                print(f"종목명 변경 감지: {code} ({old_name} -> {new_name})")
                # [핵심 수정] gspread.models.Cell은 gspread 5.0부터 삭제되어 크래시가 났습니다.
                # 최신 버전에서는 gspread.Cell을 사용합니다. (행, 열, 새 값) / 종목명은 C열 = 3번째 열
                cells_to_update.append(gspread.Cell(row_idx, 3, new_name))

    if cells_to_update:                                              # 수정할 셀이 하나라도 있으면
        print(f"총 {len(cells_to_update)}건의 변경사항을 일괄 업데이트(Overwrite)합니다.")
        sheet.update_cells(cells_to_update)                          # 모아둔 셀을 한 번의 요청으로 수정
    else:
        print("종목명/섹터가 변경된 항목이 없습니다.")

    print("구글 시트 동기화가 성공적으로 완료되었습니다.")            # 완료 안내
