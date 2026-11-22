from rest_framework import serializers
from django.contrib.auth import get_user_model
from tasks.models import Task
from subscriptions.models import UserSubscription

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    task_count = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'is_active', 'date_joined', 'task_count', 'is_staff', 'is_superuser', 'is_email_verified', 'organisation_name']

    def get_task_count(self, obj):
        return obj.tasks.count()

class AdminCreateUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    is_superuser = serializers.BooleanField(required=False, default=False)
    organisation_name = serializers.CharField(required=False, allow_blank=True)
    otp = serializers.CharField(required=False, allow_blank=True)
    zip_code = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'is_superuser', 'organisation_name', 'otp', 'zip_code']

    def create(self, validated_data):
        is_superuser = validated_data.get('is_superuser', False)
        # If superuser, also set is_staff=True so they can access admin
        is_staff = is_superuser 
        
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            organisation_name=validated_data.get('organisation_name', ''),
            otp=validated_data.get('otp', ''),
            zip_code=validated_data.get('zip_code', ''),
            is_staff=is_staff, 
            is_superuser=is_superuser,
            is_email_verified=False 
        )
        return user

class AdminUpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'is_active', 'organisation_name', 'is_superuser']
    
    def update(self, instance, validated_data):
        # Sync is_staff with is_superuser if it's being updated
        if 'is_superuser' in validated_data:
            validated_data['is_staff'] = validated_data['is_superuser']
        
        return super().update(instance, validated_data)

class AdminResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=6)

class AdminTaskSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source='user.email')
    
    class Meta:
        model = Task
        fields = ['id', 'project_name', 'status', 'deadline_date', 'user_email']

class AdminBillingSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source='user.email')
    plan_name = serializers.ReadOnlyField(source='plan.name')
    latest_invoice = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSubscription
        fields = ['id', 'user_email', 'plan_name', 'is_active', 'end_date', 'latest_invoice']

    def get_latest_invoice(self, obj):
        from subscriptions.models import Invoice
        invoice = Invoice.objects.filter(user=obj.user).order_by('-created_at').first()
        if invoice:
            return {
                'id': invoice.id,
                'amount': invoice.amount,
                'status': invoice.status,
                'created_at': invoice.created_at,
                'invoice_pdf': invoice.invoice_pdf
            }
        return None
