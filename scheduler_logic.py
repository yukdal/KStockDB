# [수정] pykrx 대신 exchange_calendars 사용
# 이유 1: 기존 코드의 stock.get_business_days_dates()는 pykrx에 존재하지 않는 함수라서 매번 크래시했습니다.
# 이유 2: "이번 주 마지막 거래일"을 알려면 '미래의 휴장일'을 알아야 하는데,
#         pykrx는 과거 시세 데이터 기반이라 미래 휴장일을 모릅니다.
# 이유 3: 최신 pykrx는 KRX 로그인 계정(KRX_ID/KRX_PW)까지 요구합니다.
# exchange_calendars는 한국거래소(XKRX) 휴장일 달력을 라이브러리 안에 내장하고 있어서
# 네트워크 접속 없이, 로그인 없이, 미래 날짜까지 정확하게 판단할 수 있습니다.

import datetime                       # 날짜 계산(오늘 날짜, 요일 등)을 위한 표준 라이브러리
import exchange_calendars as xcals    # 전 세계 거래소 휴장일 달력 라이브러리 (pip install exchange_calendars)

# 한국거래소(KRX) 달력을 프로그램 시작 시 딱 한 번만 로드해서 재사용합니다 (로드에 약간 시간이 걸리므로)
_krx_calendar = xcals.get_calendar("XKRX")   # "XKRX" = 한국거래소의 국제 표준 거래소 코드


def get_last_trading_day_of_week(target_date: datetime.date = None) -> datetime.date:
    """
    주어진 날짜가 속한 주(월~일)의 마지막 거래일을 반환합니다.
    기본값은 오늘(today)입니다. 해당 주가 전부 휴장이면 None을 반환합니다.
    """
    if target_date is None:                                # 날짜를 따로 안 넘겨줬다면
        target_date = datetime.date.today()                # 오늘 날짜를 기준으로 사용

    # weekday()는 월요일=0 ~ 일요일=6 이므로, 오늘에서 요일 숫자만큼 빼면 이번 주 월요일이 됩니다
    start_of_week = target_date - datetime.timedelta(days=target_date.weekday())
    # 월요일에 6일을 더하면 이번 주 일요일이 됩니다
    end_of_week = start_of_week + datetime.timedelta(days=6)

    # 이번 주 월요일~일요일 사이의 실제 거래일(개장일) 목록을 달력에서 조회합니다
    # (주말은 물론 설날/추석/대체공휴일 같은 휴장일도 자동으로 빠집니다)
    sessions = _krx_calendar.sessions_in_range(str(start_of_week), str(end_of_week))

    if len(sessions) == 0:                                 # 이번 주 내내 휴장인 극단적인 경우
        return None                                        # 마지막 거래일이 없으므로 None 반환

    return sessions[-1].date()                             # 거래일 목록의 맨 마지막 = 이번 주 마지막 거래일


def is_today_last_trading_day() -> bool:
    """
    오늘이 이번 주의 마지막 거래일인지 확인합니다. (맞으면 True)
    """
    today = datetime.date.today()                          # 오늘 날짜
    last_trading_day = get_last_trading_day_of_week(today) # 이번 주 마지막 거래일 계산

    return today == last_trading_day                       # 두 날짜가 같으면 True, 다르면 False


# 이 파일을 단독으로 실행했을 때만 아래 테스트 코드가 동작합니다 (python scheduler_logic.py)
if __name__ == "__main__":
    today = datetime.date.today()                                          # 오늘 날짜
    print(f"오늘: {today}")                                                # 오늘 날짜 출력
    print(f"이번 주 마지막 거래일: {get_last_trading_day_of_week(today)}")  # 계산 결과 출력
    print(f"실행 여부(is_today_last_trading_day): {is_today_last_trading_day()}")  # 오늘 실행 대상인지 출력
