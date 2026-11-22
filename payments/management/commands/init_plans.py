from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Initialize standard subscription plans'

    def handle(self, *args, **options):
        # Pro Yearly Plan
        plan, created = SubscriptionPlan.objects.get_or_create(
            name="Pro Yearly Plan",
            defaults={
                "price": 120.00,
                "duration_days": 365,
                "storage_limit_mb": 5120,
                "features": "Unlimited Projects, 5GB Storage, Priority Support"
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created "Pro Yearly Plan"'))
        else:
            self.stdout.write(self.style.WARNING('"Pro Yearly Plan" already exists'))
