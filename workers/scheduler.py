"""
Celery Beat periodic tasks.

Schedule:
  - Daily at midnight UTC: reset free-tier validation counters
  - Every hour: expire stale PENDING validations
  - Weekly: aggregate crowd insights (Pro feature)

Start Celery Beat with:
  celery -A workers.celery_app beat --loglevel=info
Or combined with worker:
  celery -A workers.celery_app worker --beat --loglevel=info
"""
import asyncio
from datetime import datetime, timedelta, date
from celery.utils.log import get_task_logger
from celery.schedules import crontab

from workers.celery_app import celery_app, run_async

logger = get_task_logger(__name__)


# ─── Beat Schedule ────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {

    # Reset free-tier daily counters every midnight UTC
    "reset-daily-counters": {
        "task": "tasks.reset_daily_counters",
        "schedule": crontab(hour=0, minute=0),  # midnight UTC
    },

    # Expire stale PENDING validations (stuck > 10 minutes) every hour
    "expire-stale-validations": {
        "task": "tasks.expire_stale_validations",
        "schedule": crontab(minute=0),  # every hour at :00
    },

    # Aggregate crowd insights weekly (Sunday 2am UTC)
    "aggregate-crowd-insights": {
        "task": "tasks.aggregate_crowd_insights",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
    },
}


# ─── Scheduled Tasks ──────────────────────────────────────────────────────────

@celery_app.task(name="tasks.reset_daily_counters")
def reset_daily_counters():
    """
    Reset daily validation counters for all free-tier users.
    Runs every midnight UTC.
    """
    async def _run():
        from db.database import get_db_context
        from db.models import User, PlanTier
        from sqlalchemy import update

        async with get_db_context() as db:
            # Bulk reset — set count=0 and date=today for all free users
            # whose last usage was yesterday
            yesterday = date.today() - timedelta(days=1)
            await db.execute(
                update(User)
                .where(
                    User.plan == PlanTier.FREE,
                    User.daily_validation_date == yesterday,
                )
                .values(daily_validation_count=0)
            )

        logger.info("Daily free-tier counters reset.")

    run_async(_run())


@celery_app.task(name="tasks.expire_stale_validations")
def expire_stale_validations():
    """
    Mark validations stuck in PENDING/PROCESSING for >10 minutes as FAILED.
    Runs every hour.
    """
    async def _run():
        from db.database import get_db_context
        from db.models import Validation, ValidationStatus
        from sqlalchemy import update

        cutoff = datetime.utcnow() - timedelta(minutes=10)

        async with get_db_context() as db:
            result = await db.execute(
                update(Validation)
                .where(
                    Validation.status.in_([
                        ValidationStatus.PENDING,
                        ValidationStatus.PROCESSING,
                    ]),
                    Validation.created_at < cutoff,
                )
                .values(
                    status=ValidationStatus.FAILED,
                    error_message="Timed out — worker did not process within 10 minutes.",
                    completed_at=datetime.utcnow(),
                )
                .returning(Validation.id)
            )
            expired_ids = result.fetchall()

        if expired_ids:
            logger.warning(f"Expired {len(expired_ids)} stale validations: {[r[0] for r in expired_ids]}")
        else:
            logger.debug("No stale validations found.")

    run_async(_run())


@celery_app.task(name="tasks.aggregate_crowd_insights")
def aggregate_crowd_insights():
    """
    Aggregate anonymized win/loss outcomes to build crowd insights.
    Runs weekly. Results stored as RAGFlow documents in the system KB.

    Crowd insights = "When RSI < 30 + MACD bullish + volume > avg,
    our users WIN 73% of the time" — premium upsell content.
    """
    async def _run():
        from db.database import get_db_context
        from db.models import Validation, ValidationStatus
        from sqlalchemy import select, func

        insights = []

        async with get_db_context() as db:
            # Get all completed validations with user-reported outcomes
            result = await db.execute(
                select(
                    Validation.ticker,
                    Validation.signal,
                    Validation.verdict,
                    Validation.confidence_score,
                    Validation.user_outcome,
                    Validation.trader_analysis,
                )
                .where(
                    Validation.status == ValidationStatus.COMPLETED,
                    Validation.user_outcome.isnot(None),
                )
                .order_by(Validation.completed_at.desc())
                .limit(1000)  # last 1000 reported trades
            )
            rows = result.fetchall()

        if len(rows) < 10:
            logger.info("Not enough outcome data yet for crowd insights (need 10+).")
            return

        # Compute accuracy stats per signal type
        stats = {}
        for row in rows:
            key = f"{row.signal}_{row.verdict}"
            if key not in stats:
                stats[key] = {"win": 0, "loss": 0, "total": 0}
            stats[key]["total"] += 1
            if row.user_outcome == "WIN":
                stats[key]["win"] += 1
            elif row.user_outcome == "LOSS":
                stats[key]["loss"] += 1

        # Build insight text
        for key, s in stats.items():
            if s["total"] < 5:
                continue
            win_rate = s["win"] / s["total"] * 100
            signal, verdict = key.split("_", 1)
            insight = (
                f"CROWD INSIGHT: When AI verdict is {verdict} for a {signal} signal, "
                f"users report a WIN rate of {win_rate:.0f}% "
                f"(based on {s['total']} reported trades)."
            )
            insights.append(insight)

        if not insights:
            return

        # Save to RAGFlow system KB
        from config.settings import settings
        from ragflow.service import RAGFlowService
        ragflow = RAGFlowService(settings)

        for i, insight in enumerate(insights):
            await ragflow.add_rule_to_dataset(
                dataset_id=settings.RAGFLOW_SYSTEM_KB_ID,
                rule_text=insight,
                rule_id=10000 + i,  # high IDs to avoid collision with base rules
            )

        logger.info(f"Crowd insights aggregated: {len(insights)} insights saved to system KB.")

    run_async(_run())
