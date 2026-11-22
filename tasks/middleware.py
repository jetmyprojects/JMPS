from .services import process_due_notifications
import logging
import threading
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class NotificationTriggerMiddleware:
    """
    Middleware to trigger deadline notification checks on authenticated requests.
    Runs at most once every minute to ensure minimal performance impact.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Only trigger on authenticated requests to avoid bot spam
        if request.user.is_authenticated:
            try:
                # check cache key
                trigger_key = "deadline_notification_trigger_lock"
                # If key exists, we checked recently (within 60s)
                if not cache.get(trigger_key):
                    # Set key immediately for 60 seconds
                    cache.set(trigger_key, "locked", 60)
                    
                    # Run in background thread
                    thread = threading.Thread(target=self.run_check)
                    thread.daemon = True
                    thread.start()
            except Exception as e:
                logger.error(f"Middleware trigger error: {e}")

        return response

    def run_check(self):
        try:
            # logger.info("Middleware triggering notification check...")
            process_due_notifications()
        except Exception as e:
            logger.error(f"Background notification check failed: {e}")

from .scheduler.runner import run_pending_tasks

class TaskSchedulerMiddleware:
    """
    Middleware to trigger the background task scheduler.
    This runs the scheduler check on every request (or sampled requests)
    in a separate thread to avoid blocking the user's response.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Trigger Scheduler after response (or concurrently)
        # Using a thread ensures we don't delay the response to the user.
        # Although in WSGI/Gunicorn, this thread will run within the worker process.
        
        # We can also check if we want to run it on EVERY request or just some.
        # For robustness, running it often is fine as valid tasks are locked.
        
        # DEBUG: Verify trigger
        # print(f"DEBUG: Middleware triggered by {request.path}", flush=True)
        


        try:
            thread = threading.Thread(target=run_pending_tasks)
            thread.daemon = True # Daemon threads exit when main program exits
            thread.start()
        except Exception as e:
            logger.error(f"Failed to start scheduler thread: {e}")

        return response
