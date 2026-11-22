from django.db.models import Sum
from tasks.models import TaskFile
from subscriptions.models import UserSubscription

def can_upload(user, new_file_size):
    """
    Checks if the user has enough storage space for a new file.
    
    Args:
        user: The user object.
        new_file_size: Size of the new file in bytes.
        
    Returns:
        bool: True if upload is allowed, False otherwise.
    """
    # Calculate used bytes
    used_bytes = get_user_storage(user)

    # Get limit based on subscription
    try:
        sub = UserSubscription.objects.get(user=user, is_active=True)
        # Check if plan exists (handle potential edge case where sub exists but plan is null)
        if sub.plan:
            limit_mb = sub.plan.storage_limit_mb
        else:
            limit_mb = 1024 # Default fallback
    except UserSubscription.DoesNotExist:
        limit_mb = 1024  # Free limit

    limit_bytes = limit_mb * 1024 * 1024

    return (used_bytes + new_file_size) <= limit_bytes

def get_user_storage(user):
    """
    Calculates the total storage used by a user in bytes.
    Args:
        user: The user object.
            
    Returns:
        int: Total size in bytes.
    """
    # Calculate total size of files across all tasks
    # Note: iterating is less efficient than DB aggregation but required since we don't store file size in a separate column
    total_bytes = 0
    # Use select_related/prefetch_related if needed, but here we just need file field
    files = TaskFile.objects.filter(task__user=user)
    for f in files:
        try:
            if f.file:
                total_bytes += f.file.size
        except Exception:
            # Handle missing files gracefully
            pass
            
    return total_bytes

def get_storage_breakdown(user):
    """
    Calculates storage usage broken down by task status.
    Returns a dict like {'ACTIVE': bytes, 'DRAFT': bytes, ...}
    """
    breakdown = {
        'ACTIVE': 0,
        'DRAFT': 0,
        'COMPLETED': 0,
        'DELETED': 0,
        'UNCOMPLETED': 0
    }
    
    # Iterate all files to ensure sum matches get_user_storage total
    files = TaskFile.objects.filter(task__user=user).select_related('task')
    
    for f in files:
        try:
            if f.file:
                size = f.file.size
                # Normalize status to uppercase key
                status = f.task.status
                if status:
                    status_key = status.upper()
                    if status_key in breakdown:
                        breakdown[status_key] += size
                    # Implicitly ignore unknown statuses or add to 'OTHER' if needed coverage
        except Exception:
            pass
        
    return breakdown
