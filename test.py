import gspread
import os
from dotenv import load_dotenv

load_dotenv()
client=gspread.service_account(filename='service_account.json')
try:
    sheet = client.open_by_key(os.getenv('SPREADSHEET_ID')).worksheet('한국종목코드')
    print(f'성공! 시트와 정상 연결되었습니다. (현재 {len(sheet.get_all_records())}개의 데이터가 있습니다.)')
except Exception as e:
    print(f"Error: {e}")
