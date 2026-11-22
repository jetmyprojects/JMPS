
# tasks/scheduler/registry.py

_registry = {}

def register_task(name):
    """
    Decorator to register a function as a scheduled task.
    Usage:
    @register_task('send_daily_digest')
    def my_task():
        ...
    """
    def decorator(func):
        _registry[name] = func
        return func
    return decorator

def get_task(name):
    return _registry.get(name)

def get_all_tasks():
    return _registry
