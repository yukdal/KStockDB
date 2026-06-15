import datetime
from pykrx import stock

def get_last_trading_day_of_week(target_date: datetime.date = None) -> datetime.date:
    """
    주어진 날짜가 속한 주의 마지막 거래일을 반환합니다.
    기본값은 오늘(today)입니다.
    """
    if target_date is None:
        target_date = datetime.date.today()
    
    # 이번 주의 월요일(0)과 일요일(6) 계산
    start_of_week = target_date - datetime.timedelta(days=target_date.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)
    
    # 해당 주간의 모든 영업일(거래일)을 가져옴
    start_str = start_of_week.strftime("%Y%m%d")
    end_str = end_of_week.strftime("%Y%m%d")
    
    b_days = stock.get_business_days_dates(start_str, end_str)
    
    if not b_days:
        return None  # 이번 주 내내 휴장인 경우 (거의 없음)
        
    return b_days[-1].date()

def is_today_last_trading_day() -> bool:
    """
    오늘이 이번 주의 마지막 거래일인지 확인합니다.
    """
    today = datetime.date.today()
    last_trading_day = get_last_trading_day_of_week(today)
    
    return today == last_trading_day

if __name__ == "__main__":
    today = datetime.date.today()
    print(f"오늘: {today}")
    print(f"이번 주 마지막 거래일: {get_last_trading_day_of_week(today)}")
    print(f"실행 여부(is_today_last_trading_day): {is_today_last_trading_day()}")
