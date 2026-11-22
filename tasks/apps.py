from django.apps import AppConfig


class TasksConfig(AppConfig):
    name = 'tasks'

    def ready(self):
        import tasks.signals
        
        # Import scheduler jobs to register them
        try:
            from tasks.scheduler import jobs
        except ImportError:
            pass
