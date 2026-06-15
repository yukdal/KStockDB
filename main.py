import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from scheduler_logic import is_today_last_trading_day
from data_fetcher import get_merged_stock_data
from sheet_updater import update_google_sheet
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def job_pipeline():
    logger.info("종목코드 스케줄러 기상! 오늘이 이번 주 마지막 거래일인지 확인합니다...")
    
    if is_today_last_trading_day():
        logger.info("오늘이 이번 주 마지막 거래일입니다. (금요일 또는 연휴 전 마지막 평일). 파이프라인 실행을 시작합니다.")
        
        max_retries = 3
        retry_delay = 60  # 1분 대기 후 재시도
        
        for attempt in range(1, max_retries + 1):
            try:
                # 1. 양사(KIS, Kiwoom) API 동시 가동 및 병합
                df = get_merged_stock_data()
                logger.info(f"데이터 교차 검증 및 병합 완료: 총 {len(df)} 종목")
                
                # 2. 구글 시트 업데이트 (신규 Insert, 변경 Update)
                update_google_sheet(df)
                
                logger.info("파이프라인이 성공적으로 수행되었습니다.")
                break  # 성공 시 루프 탈출
                
            except Exception as e:
                logger.error(f"파이프라인 실행 중 시스템 오류 발생 (시도 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    logger.info(f"{retry_delay}초 후 재시도합니다...")
                    time.sleep(retry_delay)
                else:
                    logger.critical("최대 재시도 횟수를 초과했습니다. 이번 주 업데이트를 실패로 처리합니다.")
    else:
        logger.info("오늘은 이번 주 마지막 거래일이 아닙니다. 작업을 Skip하고 내일 다시 확인합니다.")

def run_scheduler():
    scheduler = BlockingScheduler()
    # 매주 월~금 오후 17시 30분에 실행 (Dyna-Calendar 스케줄링)
    scheduler.add_job(job_pipeline, 'cron', day_of_week='mon-fri', hour=17, minute=30, timezone='Asia/Seoul')
    
    logger.info("==================================================")
    logger.info(" [Dyna-Calendar] 백그라운드 크론 파이프라인 가동")
    logger.info(" 대기 스케줄: 매주 평일 17:30")
    logger.info("==================================================")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러가 종료되었습니다.")

if __name__ == "__main__":
    load_dotenv()
    
    # [수동 즉시 실행 모드] 
    # 처음 구축 후 시트에 데이터가 잘 써지는지 바로 테스트하고 싶으시면 아래 두 줄의 주석을 해제하세요.
    # print("==== [수동 파이프라인 강제 실행 테스트] ====")
    # job_pipeline()
    
    # 기본 모드: 백그라운드 스케줄러 모드
    run_scheduler()
