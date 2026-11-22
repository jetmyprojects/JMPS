from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Initializes default subscription plans'

    def handle(self, *args, **options):
        self.stdout.write('Checking for subscription plans...')
        
        plan, created = SubscriptionPlan.objects.update_or_create(
            name="Pro Yearly Plan",
            defaults={
                'price': 120.00,
                'duration_days': 365,
                'features': "Unlimited Projects, AI Assistance",
                'storage_limit_mb': 5120
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Successfully created plan: {plan.name}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated plan: {plan.name}'))
