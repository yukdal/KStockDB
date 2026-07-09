import gspread                     # 구글 스프레드시트 라이브러리
import os                          # 환경변수 읽기용
from dotenv import load_dotenv     # .env 파일 로드용

load_dotenv()                      # .env 내용을 환경변수로 읽어들임

client = gspread.service_account(filename='service_account.json')   # 서비스 계정으로 구글 인증

try:
    spreadsheet = client.open_by_key(os.getenv('SPREADSHEET_ID'))    # 스프레드시트 파일 열기
    print(f"성공! 스프레드시트와 정상 연결되었습니다. (제목: {spreadsheet.title})")

    # 자동 관리 전용 탭 확인 (.env의 WORKSHEET_NAME, 기본값 "한국종목코드_자동")
    worksheet_name = os.getenv("WORKSHEET_NAME", "한국종목코드_자동")
    try:
        sheet = spreadsheet.worksheet(worksheet_name)                # 전용 탭 열기 시도
        # get_all_values()는 제목 줄이 중복돼도 에러가 나지 않는 안전한 읽기 방식입니다
        row_count = max(len(sheet.get_all_values()) - 1, 0)          # 헤더 제외 데이터 행 수
        print(f"'{worksheet_name}' 탭 확인: 현재 {row_count}개의 종목이 있습니다.")
    except gspread.WorksheetNotFound:                                # 아직 탭이 없으면
        print(f"'{worksheet_name}' 탭은 아직 없습니다. 첫 업데이트 실행 시 자동으로 생성됩니다.")
except Exception as e:
    print(f"Error: {e}")
