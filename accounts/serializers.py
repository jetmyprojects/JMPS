from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'organisation_name', 'zip_code', 'is_email_verified']

class UserProfileSerializer(serializers.ModelSerializer):
    is_premium = serializers.SerializerMethodField()
    is_trial = serializers.SerializerMethodField()
    subscription_end_date = serializers.SerializerMethodField()
    has_used_trial_or_subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'organisation_name', 'zip_code', 'timezone', 'is_email_verified', 'is_superuser', 'date_joined', 'is_premium', 'is_trial', 'subscription_end_date', 'has_used_trial_or_subscription']
        read_only_fields = ['id', 'username', 'email', 'is_email_verified', 'is_superuser', 'date_joined', 'is_premium', 'is_trial', 'subscription_end_date', 'has_used_trial_or_subscription']

    def get_is_premium(self, obj):
        try:
            if obj.is_staff or obj.is_superuser:
                return True
            subscription = obj.subscription
            from django.utils import timezone
            return subscription.is_active and subscription.end_date >= timezone.now().date()
        except:
            return False

    def get_is_trial(self, obj):
        try:
            subscription = obj.subscription
            if subscription.is_active and subscription.stripe_payment_intent and str(subscription.stripe_payment_intent).startswith('TRIAL-CODE'):
                return True
            return False
        except:
            return False

    def get_subscription_end_date(self, obj):
        try:
            subscription = obj.subscription
            if subscription.is_active:
                return subscription.end_date
            return None
        except:
            return None

    def get_has_used_trial_or_subscription(self, obj):
        # Check if user has any Invoice (paid or trial) OR if subscription exists (even if inactive)
        # Actually simplest is to check if they have ever had a subscription record or invoice
        # If they have a UserSubscription record, they likely started a flow.
        # But maybe better to check Invoices to be sure they actually "used" it?
        # UserSubscription is created on signup sometimes? No, usually on payment/trial start.
        # Let's check if UserSubscription exists.
        try:
            return hasattr(obj, 'subscription')
        except:
            return False

class RegisterSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    # Rename input field to match model field for clarity
    organisation_name = serializers.CharField(write_only=True, required=False) 
    zip_code = serializers.CharField(required=False)
    timezone = serializers.CharField(required=False) # Newly added
    referral_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'organisation_name', 'zip_code', 'timezone', 'referral_code']

    def validate_email(self, value):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        
        value = value.lower()
        try:
            validate_email(value)
        except ValidationError:
             raise serializers.ValidationError("Enter a valid email address.")
        return value

    def validate_zip_code(self, value):
        if len(str(value).strip()) < 5:
             raise serializers.ValidationError("Zip code must be at least 5 characters.")
        return value

    def create(self, validated_data):
        # Extract extra fields
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        organisation_name = validated_data.get('organisation_name', '')
        zip_code = validated_data.get('zip_code', '')
        timezone = validated_data.get('timezone', 'UTC') # Default to UTC if not provided

        # Check if user already exists
        existing_user = User.objects.filter(email=validated_data['email']).first()
        if existing_user:
            # Mark as existing so view can handle it (e.g. skip referral logic)
            existing_user._is_existing_user = True
            return existing_user

        # Use email as username to ensure uniqueness
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=first_name,
            last_name=last_name,
            organisation_name=organisation_name,
            zip_code=zip_code,
            timezone=timezone # Save detected timezone
        )
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate_email(self, value):
        return value.lower()

    def validate(self, data):
        # Email is already lowercased by validate_email before reaching here
        user = authenticate(username=data.get('email'), password=data.get('password'))
        if user and user.is_active:
            if not user.is_email_verified and not user.is_superuser:
                raise serializers.ValidationError("Email is not verified. Please verify your OTP.")
            return user
        raise serializers.ValidationError("Incorrect Credentials")

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower()

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_email(self, value):
        return value.lower()

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])


