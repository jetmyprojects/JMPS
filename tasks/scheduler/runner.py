
# tasks/scheduler/runner.py
import logging
import traceback
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from tasks.models import ScheduledTask
from .registry import get_task

logger = logging.getLogger(__name__)

def run_pending_tasks():
    """
    Check for pending tasks and execute them.
    This function is safe to run concurrently across multiple workers.
    """
    now = timezone.now()
    
    # 1. Provide a quick check (non-locking) to avoid transaction overhead if nothing to do
    # This is optimization.
    has_pending = ScheduledTask.objects.filter(next_run_at__lte=now).exists()
    if not has_pending:
        return

    # 2. Iterate and attempt to lock
    # We fetch IDs first to keep the loop tight, but we could just iterate the queryset loop with lock.
    # However, skip_locked is best used with a limit or specific selection.
    
    pending_tasks = ScheduledTask.objects.filter(next_run_at__lte=now)
    
    for task_instance in pending_tasks:
        # Start a transaction for each task to ensure atomic locking and execution
        try:
            with transaction.atomic():
                # SELECT ... FOR UPDATE SKIP LOCKED
                # This ensures that if another worker picked this up, we skip it.
                # Refresh from DB with lock.
                locked_task = ScheduledTask.objects.select_for_update(skip_locked=True).filter(id=task_instance.id).first()
                
                if not locked_task:
                    # Already locked by someone else or deleted
                    continue

                # Double check time (in case it was just updated by another worker before we got lock - unlikely with skip_locked but good practice)
                if locked_task.next_run_at > timezone.now():
                    continue

                logger.info(f"Scheduler: Executing task '{locked_task.name}'")
                
                # Execute the actual function
                task_func = get_task(locked_task.name)
                
                if task_func:
                    try:
                        task_func()
                        logger.info(f"Scheduler: Task '{locked_task.name}' completed successfully.")
                    except Exception as e:
                        logger.error(f"Scheduler: Task '{locked_task.name}' failed: {e}")
                        logger.error(traceback.format_exc())
                else:
                    logger.error(f"Scheduler: Task '{locked_task.name}' not found in registry.")

                # Update state
                locked_task.last_run_at = timezone.now()
                # Schedule next run
                # Simple interval based. ideally we'd have crontab syntax support but interval is requirement.
                locked_task.next_run_at = timezone.now() + timedelta(seconds=locked_task.interval_seconds)
                locked_task.save()
                
        except Exception as e:
             logger.error(f"Scheduler: Error in run_pending_tasks loop: {e}")
