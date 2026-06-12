from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db.models import Q
from djongo import models as djongo_models
from djongo.models import GenericObjectIdField, django_models
from bson import ObjectId


class CustomUserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address.')
        email = self.normalize_email(email)
        # Username is not required; use email as username (email is unique, so username stays unique)
        extra_fields.pop('username', None)
        extra_fields.setdefault('username', email[:150])
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password=password, **extra_fields)


class CustomUser(AbstractUser):
    """Primary key is MongoDB _id (ObjectId) so djongo never passes ObjectId to an integer field."""
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    objects = CustomUserManager()
    email = models.EmailField("email address", unique=True, blank=False)
    # Not required; stored as email when unset (USERNAME_FIELD is email).
    username = models.CharField(
        max_length=150, unique=True, blank=True, null=True,
        help_text="Optional. Defaults to email.",
    )

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        OTHER = 'other', 'Other'

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.ADMIN
    )
    agent_name = models.CharField(max_length=100, blank=True, default="Lindiwe")
    phone = models.CharField(max_length=15, blank=True, null=True)
    voicelink_did = models.CharField(max_length=20, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.PositiveIntegerField(default=0)

    class Meta(AbstractUser.Meta):
        db_table = 'api_customuser'
        constraints = [
            models.UniqueConstraint(
                fields=['phone'],
                condition=Q(phone__isnull=False) & ~Q(phone=''),
                name='unique_customuser_phone_non_empty',
            ),
            models.UniqueConstraint(
                fields=['voicelink_did'],
                condition=Q(voicelink_did__isnull=False) & ~Q(voicelink_did=''),
                name='unique_customuser_voicelink_did',
            ),
        ]

    def save(self, *args, **kwargs):
        if not (self.username or '').strip() and self.email:
            self.username = self.email[:150]

        super().save(*args, **kwargs)


class UserProfile(models.Model):
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    profile_image = models.URLField(max_length=500, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username or self.user.email}'s Profile"


class Call(djongo_models.Model):
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)

    call_sid = models.CharField(max_length=128, blank=True, null=True, db_index=True)  # Exotel CallSid (unique ideally)
    direction = models.CharField(max_length=16, blank=True, null=True)  # inbound/outbound
    from_number = models.CharField(max_length=32, blank=True, null=True)
    to_number = models.CharField(max_length=32, blank=True, null=True)

    call_type = models.CharField(max_length=50, blank=True, null=True) 
    call_status = models.CharField(max_length=50, blank=True, null=True, db_index=True)

    call_date = models.DateTimeField(blank=True, null=True)        # (can be start_time)
    call_created_at = models.DateTimeField(blank=True, null=True)  # when record created
    call_end_at = models.DateTimeField(blank=True, null=True)      # REQUIRED for webhook completion
    call_duration = models.IntegerField(blank=True, null=True)     # seconds

    call_recording_url = models.URLField(max_length=500, blank=True, null=True)  # Exotel recording URL
    call_recording_url_s3 = models.URLField(max_length=500, blank=True, null=True) 
    recording_fetched_at = models.DateTimeField(blank=True, null=True)  

    transcript = djongo_models.JSONField(blank=True, null=True)

    ai_analysis_status = models.CharField(max_length=50, blank=True, null=True)  # pending/completed/failed
    ai_analysis_updated_at = models.DateTimeField(blank=True, null=True)
    ai_analysis_error = models.TextField(blank=True, null=True)

    sentiment = models.CharField(max_length=32, blank=True, null=True)  # positive/neutral/negative
    feedback_given = models.BooleanField(blank=True, null=True)
    issues_raised = djongo_models.JSONField(blank=True, null=True)  # optional list of issue categories
    conversation_summary = models.TextField(blank=True, null=True)

    call_notes = models.TextField(blank=True, null=True)
    call_feedback = models.TextField(blank=True, null=True)
    call_rating = models.IntegerField(blank=True, null=True)

    phone_number = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=200, blank=True, null=True)

    error_reason = models.TextField(blank=True, null=True)
    dnd_status = models.BooleanField(blank=True, null=True)
    didnt_interact = models.CharField(max_length=10, blank=True, null=True, default="no") # "yes" or "no"

    class Meta:
        db_table = "api_calls"


class Prompt(djongo_models.Model):
    id = None
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)
    service_id = GenericObjectIdField()
    # Not globally unique: each bus service (provider) has its own row per prompt_type.
    prompt_type = models.CharField(max_length=50, blank=False)
    title = models.CharField(max_length=200, blank=False)
    icon = models.CharField(max_length=250, blank=True, null=True)
    prompt_text = models.TextField(blank=False)

    class Meta:
        db_table = "prompts"
        unique_together = [["service_id", "prompt_type"]]


class FirozLalani(djongo_models.Model):
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    email = models.EmailField(blank=True, null=True)
    dob = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    support_person = models.CharField(max_length=100, blank=True, null=True)
    appointment_type = models.CharField(max_length=100, blank=True, null=True)
    preferred_day = models.CharField(max_length=100, blank=True, null=True)
    time_preference = models.CharField(max_length=100, blank=True, null=True)
    selected_slot = models.CharField(max_length=100, blank=True, null=True)
    call_outcome = models.CharField(max_length=100, blank=True, null=True)
    patient_status = models.CharField(max_length=100, blank=True, null=True)
    booking_status = models.CharField(max_length=20, default='pending')
    ghl_appointment_id = models.CharField(max_length=100, blank=True, null=True)
    message_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        db_table = "firoz_lalani"

    def __str__(self):
        name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return name if name else f"FirozLalani - {self.phone or 'No Phone'}"


class KnowledgeBase(djongo_models.Model):
    _id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId, editable=False)
    category = models.CharField(max_length=50, default='general')
    question = models.TextField()
    answer = models.TextField()
    keywords = djongo_models.JSONField(default=list, blank=True)
    
    # Optional fields for pricing rules
    procedure_name = models.CharField(max_length=255, blank=True, null=True)
    starting_price = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "knowledge_base"

    def __str__(self):
        return f"[{self.category.upper()}] {self.question[:50]}"