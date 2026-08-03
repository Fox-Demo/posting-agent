"""Post scheduler using APScheduler."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from auto_posting.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """Scheduled job information."""

    job_id: str
    name: str
    next_run: datetime | None
    trigger_type: str
    is_paused: bool = False


@dataclass
class PostScheduler:
    """
    Schedule automated posts using APScheduler.

    Supports interval-based and cron-based scheduling.
    """

    settings: Settings
    _scheduler: AsyncIOScheduler = field(init=False)
    _job_callbacks: dict[str, Callable] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timezone = ZoneInfo(self.settings.scheduler.timezone)

        self._scheduler = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Only one instance of each job
                "misfire_grace_time": 3600,  # 1 hour grace period
            },
        )

        # Add event listeners
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle job execution events."""
        job_id = event.job_id

        if event.exception:
            logger.error(
                f"Job {job_id} failed with exception: {event.exception}",
                exc_info=event.exception,
            )
        else:
            logger.info(f"Job {job_id} executed successfully")

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Scheduler stopped")

    def add_interval_job(
        self,
        job_id: str,
        func: Callable,
        hours: int | None = None,
        minutes: int | None = None,
        seconds: int | None = None,
        start_date: datetime | None = None,
        **kwargs: Any,
    ) -> ScheduledJob:
        """
        Add a job that runs at fixed intervals.

        Args:
            job_id: Unique job identifier
            func: Async function to run
            hours: Interval in hours
            minutes: Interval in minutes
            seconds: Interval in seconds
            start_date: When to start (default: now)
            **kwargs: Additional arguments to pass to the function

        Returns:
            ScheduledJob info
        """
        if hours is None and minutes is None and seconds is None:
            hours = self.settings.scheduler.default_interval_hours

        trigger = IntervalTrigger(
            hours=hours or 0,
            minutes=minutes or 0,
            seconds=seconds or 0,
            start_date=start_date,
        )

        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            kwargs=kwargs,
            replace_existing=True,
        )

        self._job_callbacks[job_id] = func
        logger.info(f"Added interval job: {job_id}")

        return ScheduledJob(
            job_id=job_id,
            name=job_id,
            next_run=job.next_run_time,
            trigger_type="interval",
        )

    def add_cron_job(
        self,
        job_id: str,
        func: Callable,
        hour: int | str = "*",
        minute: int | str = "0",
        day_of_week: str = "*",
        **kwargs: Any,
    ) -> ScheduledJob:
        """
        Add a job that runs on a cron schedule.

        Args:
            job_id: Unique job identifier
            func: Async function to run
            hour: Hour(s) to run (0-23 or cron expression)
            minute: Minute(s) to run (0-59 or cron expression)
            day_of_week: Days to run (mon-sun or 0-6)
            **kwargs: Additional arguments to pass to the function

        Returns:
            ScheduledJob info
        """
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )

        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            kwargs=kwargs,
            replace_existing=True,
        )

        self._job_callbacks[job_id] = func
        logger.info(f"Added cron job: {job_id} (hour={hour}, minute={minute})")

        return ScheduledJob(
            job_id=job_id,
            name=job_id,
            next_run=job.next_run_time,
            trigger_type="cron",
        )

    def add_daily_jobs(
        self,
        job_id_prefix: str,
        func: Callable,
        times: list[tuple[int, int]],
        **kwargs: Any,
    ) -> list[ScheduledJob]:
        """
        Add jobs that run at specific times each day.

        Args:
            job_id_prefix: Prefix for job IDs
            func: Async function to run
            times: List of (hour, minute) tuples
            **kwargs: Additional arguments

        Returns:
            List of ScheduledJob info
        """
        jobs = []

        for i, (hour, minute) in enumerate(times):
            job_id = f"{job_id_prefix}_{i}"
            job = self.add_cron_job(
                job_id=job_id,
                func=func,
                hour=hour,
                minute=minute,
                **kwargs,
            )
            jobs.append(job)

        return jobs

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self._scheduler.remove_job(job_id)
            self._job_callbacks.pop(job_id, None)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id}: {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to pause job {job_id}: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to resume job {job_id}: {e}")
            return False

    def get_jobs(self) -> list[ScheduledJob]:
        """Get all scheduled jobs."""
        jobs = []

        for job in self._scheduler.get_jobs():
            trigger_type = type(job.trigger).__name__.replace("Trigger", "").lower()

            jobs.append(
                ScheduledJob(
                    job_id=job.id,
                    name=job.name,
                    next_run=job.next_run_time,
                    trigger_type=trigger_type,
                    is_paused=job.next_run_time is None,
                )
            )

        return jobs

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Get a specific job."""
        job = self._scheduler.get_job(job_id)

        if job is None:
            return None

        trigger_type = type(job.trigger).__name__.replace("Trigger", "").lower()

        return ScheduledJob(
            job_id=job.id,
            name=job.name,
            next_run=job.next_run_time,
            trigger_type=trigger_type,
            is_paused=job.next_run_time is None,
        )

    async def run_job_now(self, job_id: str) -> None:
        """Manually trigger a job to run immediately."""
        job = self._scheduler.get_job(job_id)

        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        logger.info(f"Manually triggering job: {job_id}")
        await job.func(**job.kwargs)

    def reschedule_job(
        self,
        job_id: str,
        hours: int | None = None,
        minutes: int | None = None,
    ) -> ScheduledJob | None:
        """Reschedule an interval job with new timing."""
        job = self._scheduler.get_job(job_id)

        if job is None:
            return None

        trigger = IntervalTrigger(
            hours=hours or 0,
            minutes=minutes or 0,
        )

        self._scheduler.reschedule_job(job_id, trigger=trigger)

        return self.get_job(job_id)
