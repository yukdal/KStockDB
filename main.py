import logging          # 실행 기록(로그)을 남기기 위한 표준 라이브러리
import time             # 재시도 전 대기(sleep)를 위한 표준 라이브러리
from apscheduler.schedulers.blocking import BlockingScheduler   # 정해진 시각에 작업을 실행해주는 스케줄러
from dotenv import load_dotenv                                  # .env 파일을 환경변수로 읽는 라이브러리

load_dotenv()           # [수정] 다른 모듈을 import 하기 '전에' .env를 먼저 로드 (설정 누락 사고 방지)

import os                                                       # 환경변수(.env 값) 읽기용
from scheduler_logic import is_today_last_trading_day           # "오늘이 이번 주 마지막 거래일인가?" 판단 함수
from data_fetcher import get_merged_stock_data                  # 전체 종목 데이터를 수집/병합하는 함수
from sheet_updater import update_google_sheet, overwrite_worksheet  # 시트 동기화 / 전체 새로고침 함수
from krx_fetcher import fetch_stock_basic_info, fetch_etf_basic_info  # KRX 주식/ETF 기본정보 수집 함수

# 로그 형식 설정: 시간 - 모듈이름 - 레벨 - 메시지
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)                            # 이 파일 전용 로거 생성


def update_basic_info_sheets():
    """KRX에서 주식/ETF 기본정보(상장일, 액면가, 총보수 등)를 받아 전용 탭 2개를 통째로 새로고침합니다.
    핵심 기능(티커 동기화)과 분리되어 있어서, 여기서 실패해도 티커 업데이트 결과는 유지됩니다."""
    # 주식 기본정보 탭 (.env의 STOCK_INFO_WORKSHEET로 이름 변경 가능)
    try:
        stock_info = fetch_stock_basic_info()                   # KRX에서 주식 12열 기본정보 수집
        overwrite_worksheet(stock_info, os.getenv("STOCK_INFO_WORKSHEET", "주식기본정보_자동"))
    except Exception as e:                                      # KRX 차단/점검 등으로 실패해도
        logger.error(f"주식 기본정보 업데이트 실패 (티커 동기화에는 영향 없음): {e}")

    # ETF 기본정보 탭 (.env의 ETF_INFO_WORKSHEET로 이름 변경 가능)
    try:
        etf_info = fetch_etf_basic_info()                       # KRX에서 ETF 기본정보 수집
        overwrite_worksheet(etf_info, os.getenv("ETF_INFO_WORKSHEET", "ETF기본정보_자동"))
    except Exception as e:                                      # 실패해도 나머지 결과는 유지
        logger.error(f"ETF 기본정보 업데이트 실패 (티커 동기화에는 영향 없음): {e}")


def job_pipeline():
    """매일 17:30에 깨어나서, 오늘이 이번 주 마지막 거래일일 때만 실제 작업을 수행합니다."""
    logger.info("종목코드 스케줄러 기상! 오늘이 이번 주 마지막 거래일인지 확인합니다...")

    if is_today_last_trading_day():                             # 오늘이 마지막 거래일이면 (금요일 또는 연휴 전 평일)
        logger.info("오늘이 이번 주 마지막 거래일입니다. 파이프라인 실행을 시작합니다.")

        max_retries = 3                                         # 실패 시 최대 3번까지 시도
        retry_delay = 60                                        # 실패하면 60초 쉬고 재시도

        for attempt in range(1, max_retries + 1):               # 1번째, 2번째, 3번째 시도
            try:
                # 1. 종목 데이터 수집 및 병합 (KIS 마스터파일 → 실패 시 pykrx)
                df = get_merged_stock_data()
                logger.info(f"데이터 교차 검증 및 병합 완료: 총 {len(df)} 종목")

                # 2. 구글 시트 업데이트 (신규 Insert, 변경 Update)
                update_google_sheet(df)

                # 3. KRX 주식/ETF 기본정보 전체 새로고침 (실패해도 1~2번 결과에는 영향 없음)
                update_basic_info_sheets()

                logger.info("파이프라인이 성공적으로 수행되었습니다.")
                break                                           # 성공했으니 재시도 루프 종료
            except Exception as e:                              # 어떤 단계든 실패하면
                logger.error(f"파이프라인 실행 중 시스템 오류 발생 (시도 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:                       # 아직 시도 횟수가 남았으면
                    logger.info(f"{retry_delay}초 후 재시도합니다...")
                    time.sleep(retry_delay)                     # 60초 대기
                else:                                           # 3번 모두 실패하면
                    logger.critical("최대 재시도 횟수를 초과했습니다. 이번 주 업데이트를 실패로 처리합니다.")
    else:                                                       # 오늘이 마지막 거래일이 아니면
        logger.info("오늘은 이번 주 마지막 거래일이 아닙니다. 작업을 Skip하고 내일 다시 확인합니다.")


def run_scheduler():
    """백그라운드 스케줄러를 시작합니다. (프로그램이 계속 켜져 있어야 합니다)"""
    scheduler = BlockingScheduler()                             # 프로그램을 점유하며 도는 스케줄러 생성
    # 매주 월~금 오후 17시 30분(한국시간)에 job_pipeline 실행
    # [수정] misfire_grace_time=3600 : 서버가 재부팅/일시정지 등으로 17:30을 놓쳐도
    #        1시간 이내에 복구되면 밀린 작업을 실행해줍니다. (기본값은 1초라 조금만 늦어도 그냥 건너뜀)
    # [수정] coalesce=True : 여러 번 밀렸어도 몰아서 1번만 실행합니다.
    scheduler.add_job(job_pipeline, 'cron', day_of_week='mon-fri', hour=17, minute=30,
                      timezone='Asia/Seoul', misfire_grace_time=3600, coalesce=True)

    logger.info("==================================================")
    logger.info(" 백그라운드 크론 파이프라인 가동")
    logger.info(" 대기 스케줄: 매주 평일 17:30 (KST)")
    logger.info("==================================================")
    try:
        scheduler.start()                                       # 스케줄러 시작 (여기서 계속 대기)
    except (KeyboardInterrupt, SystemExit):                     # Ctrl+C 등으로 종료 시
        logger.info("스케줄러가 종료되었습니다.")


if __name__ == "__main__":                                      # 이 파일을 직접 실행했을 때만 동작
    # [수동 즉시 실행 모드]
    # 시트에 데이터가 잘 써지는지 바로 테스트하고 싶으면 아래 두 줄의 주석(#)을 지우세요.
    # print("==== [수동 파이프라인 강제 실행 테스트] ====")
    # job_pipeline()

    # 기본 모드: 백그라운드 스케줄러 모드
    run_scheduler()
