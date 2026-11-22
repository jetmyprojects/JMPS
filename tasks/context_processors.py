def user_context(request):
    """
    Adds user-specific context to all templates.
    """
    if request.user.is_authenticated:
        # Get first name or username or email
        display_name = request.user.first_name or request.user.username or request.user.email
        
        return {
            "display_name": display_name,
            "is_admin": request.user.is_superuser,
            "user_timezone": getattr(request.user, 'timezone', 'UTC')
        }
    return {
        "display_name": "User",
        "is_admin": False,
        "user_timezone": "UTC"
    }
