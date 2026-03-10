import asyncio
import logging
from datetime import datetime
from scanner import ArbitrageScanner
from config import TELEGRAM_TOKEN, CHAT_ID, CHECK_INTERVAL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scanner = ArbitrageScanner(TELEGRAM_TOKEN, CHAT_ID)

async def scan_job():
    logger.info(f"🔍 Сканування запущено о {datetime.now()}")
    await scanner.scan_all()

async def main():
    logger.info("🚀 Бот автоматичного пошуку спредів запущений!")
    while True:
        await scan_job()
        logger.info(f"⏱ Чекаю {CHECK_INTERVAL} секунд до наступного сканування")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())