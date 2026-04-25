"""
Async validation tasks that run in Celery workers.

Each task:
  1. Processes the validation request (OpenTrade.ai + RAGFlow)
  2. Saves result to database
  3. Sends Telegram message to user
"""
import asyncio
from datetime import datetime
from typing import Optional
from celery.utils.log import get_task_logger

from workers.celery_app import celery_app, run_async
from services.validation import ValidationService
from db.database import get_db_context
from db.models import Validation, ValidationStatus, User
from sqlalchemy import select

logger = get_task_logger(__name__)


def _get_validation_service():
    """Create a ValidationService instance (one per task)."""
    return ValidationService()


@celery_app.task(bind=True, name="tasks.validate_manual", max_retries=2)
def validate_manual_task(
    self,
    validation_id: int,
    telegram_id: int,
    ticker: str,
    signal: str,
    price: Optional[float],
    ragflow_dataset_id: Optional[str],
):
    """
    Product 3: Process a manual validation request.
    Called after /check AAPL BUY 175 command.
    """
    logger.info(f"[Task] Manual validation: {ticker} {signal} for user {telegram_id}")

    async def _run():
        service = _get_validation_service()
        try:
            result = await service.validate_manual(
                ticker=ticker,
                signal=signal,
                price=price,
                user_ragflow_dataset_id=ragflow_dataset_id,
            )

            async with get_db_context() as db:
                # Update validation record
                stmt = select(Validation).where(Validation.id == validation_id)
                db_result = await db.execute(stmt)
                validation = db_result.scalar_one_or_none()

                if validation:
                    validation.status = ValidationStatus.COMPLETED
                    validation.confidence_score = result["confidence_score"]
                    validation.verdict = result["verdict"]
                    validation.trader_analysis = result["trader_analysis"]
                    validation.mentor_context = result["mentor_context"]
                    validation.final_message = result["final_message"]
                    validation.completed_at = datetime.utcnow()

            # Send Telegram message
            await _send_telegram_message(telegram_id, result["final_message"])
            logger.info(f"[Task] Manual validation complete for {ticker}, verdict={result['verdict']}")

        except Exception as e:
            logger.error(f"[Task] Manual validation failed: {e}")
            await _update_validation_failed(validation_id, str(e))
            await _send_telegram_message(
                telegram_id,
                f"❌ Analysis failed for *{ticker}*. Please try again.\n\n_Error: {str(e)[:100]}_"
            )
            raise self.retry(exc=e, countdown=30)

    run_async(_run())


@celery_app.task(bind=True, name="tasks.validate_indicator", max_retries=2)
def validate_indicator_task(
    self,
    validation_id: int,
    telegram_id: int,
    ticker: str,
    signal: str,
    price: Optional[float],
    indicator_name: str,
    ragflow_dataset_id: Optional[str],
    extra_payload: Optional[dict] = None,
):
    """
    Product 1: Process an indicator webhook validation.
    Called when TradingView sends a signal.
    """
    logger.info(f"[Task] Indicator validation: {ticker} {signal} from {indicator_name}")

    async def _run():
        service = _get_validation_service()
        try:
            result = await service.validate_indicator(
                ticker=ticker,
                signal=signal,
                price=price,
                indicator_name=indicator_name,
                user_ragflow_dataset_id=ragflow_dataset_id,
                extra_payload=extra_payload,
            )

            async with get_db_context() as db:
                stmt = select(Validation).where(Validation.id == validation_id)
                db_result = await db.execute(stmt)
                validation = db_result.scalar_one_or_none()

                if validation:
                    validation.status = ValidationStatus.COMPLETED
                    validation.confidence_score = result["confidence_score"]
                    validation.verdict = result["verdict"]
                    validation.trader_analysis = result["trader_analysis"]
                    validation.mentor_context = result["mentor_context"]
                    validation.final_message = result["final_message"]
                    validation.completed_at = datetime.utcnow()

            message = result["final_message"]
            # Prepend indicator source info
            indicator_header = f"*📡 Indicator Alert: {indicator_name}*\n\n"
            await _send_telegram_message(telegram_id, indicator_header + message)

        except Exception as e:
            logger.error(f"[Task] Indicator validation failed: {e}")
            await _update_validation_failed(validation_id, str(e))
            await _send_telegram_message(
                telegram_id,
                f"❌ Failed to validate *{indicator_name}* signal for *{ticker}*.\n\n_Error: {str(e)[:100]}_"
            )
            raise self.retry(exc=e, countdown=30)

    run_async(_run())


@celery_app.task(bind=True, name="tasks.analyze_ea", max_retries=2)
def analyze_ea_task(
    self,
    validation_id: int,
    telegram_id: int,
    ticker: str,
    action: str,
    result_outcome: str,
    pnl: Optional[float],
    ea_name: str,
    trade_time: Optional[str],
    ragflow_dataset_id: Optional[str],
):
    """
    Product 2: Analyze an EA trade result.
    Called when the EA monitoring script sends a trade log.
    """
    logger.info(f"[Task] EA analysis: {ea_name} {action} {ticker} → {result_outcome}")

    async def _run():
        service = _get_validation_service()
        try:
            result = await service.analyze_ea_trade(
                ticker=ticker,
                action=action,
                result_outcome=result_outcome,
                pnl=pnl,
                ea_name=ea_name,
                trade_time=trade_time,
                user_ragflow_dataset_id=ragflow_dataset_id,
            )

            async with get_db_context() as db:
                stmt = select(Validation).where(Validation.id == validation_id)
                db_result = await db.execute(stmt)
                validation = db_result.scalar_one_or_none()

                if validation:
                    validation.status = ValidationStatus.COMPLETED
                    validation.confidence_score = result["confidence_score"]
                    validation.verdict = result["verdict"]
                    validation.trader_analysis = result["trader_analysis"]
                    validation.mentor_context = result["mentor_context"]
                    validation.final_message = result["final_message"]
                    validation.completed_at = datetime.utcnow()

            await _send_telegram_message(telegram_id, result["final_message"])

        except Exception as e:
            logger.error(f"[Task] EA analysis failed: {e}")
            await _update_validation_failed(validation_id, str(e))
            await _send_telegram_message(
                telegram_id,
                f"❌ Failed to analyze *{ea_name}* trade on *{ticker}*.\n\n_Error: {str(e)[:100]}_"
            )
            raise self.retry(exc=e, countdown=30)

    run_async(_run())


# ─── Helper functions ─────────────────────────────────────────────────────────

async def _send_telegram_message(telegram_id: int, text: str):
    """Send a message to a Telegram user from the worker."""
    import httpx
    from config.settings import settings

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {telegram_id}: {e}")


async def _update_validation_failed(validation_id: int, error_msg: str):
    """Mark a validation record as failed in the database."""
    async with get_db_context() as db:
        stmt = select(Validation).where(Validation.id == validation_id)
        result = await db.execute(stmt)
        validation = result.scalar_one_or_none()
        if validation:
            validation.status = ValidationStatus.FAILED
            validation.error_message = error_msg[:500]
            validation.completed_at = datetime.utcnow()
