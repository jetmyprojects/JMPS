from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from tasks.models import TaskFile
from subscriptions.models import UserSubscription
import logging

logger = logging.getLogger('django')

class StorageUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Aggregate total file size directly from DB
        from storage.utils import get_user_storage
        total_bytes = get_user_storage(user)
        logger.error(f"DEBUG STORAGE: User={user.email} (ID={user.id}), TotalBytes={total_bytes}")

        # Breakdown by task status
        breakdown = {}
        statuses = ['ACTIVE', 'DRAFT', 'COMPLETED', 'DELETED']

        for status in statuses:
            # Revert to python iteration for size calculation
            status_files = TaskFile.objects.filter(
                task__user=user,
                task__status=status,
                file__isnull=False
            )
            size = 0
            for f in status_files:
                try:
                    if f.file:
                        size += f.file.size
                except Exception:
                    pass
            breakdown[status] = size

        # Convert to MB
        used_mb = round(total_bytes / (1024 * 1024), 2)
        breakdown_mb = {k: round(v / (1024 * 1024), 2) for k, v in breakdown.items()}

        return Response({
            "used_bytes": total_bytes,
            "used_mb": used_mb,
            "breakdown_bytes": breakdown,
            "breakdown_mb": breakdown_mb
        })

class StorageLimitView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        limit_mb = 1024 # Default free limit
        plan_name = "Free"
        
        try:
            sub = UserSubscription.objects.get(user=user, is_active=True)
            if sub.plan:
                limit_mb = sub.plan.storage_limit_mb
                plan_name = sub.plan.name
        except UserSubscription.DoesNotExist:
            pass
            
        logger.error(f"DEBUG LIMIT: User={user.email}, Limit={limit_mb}, Plan={plan_name}")
            
        return Response({
            "limit_mb": limit_mb,
            "plan_name": plan_name
        })
