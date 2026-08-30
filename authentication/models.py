import uuid

from django.db import models
from django.utils import timezone


class User(models.Model):
    user_id = models.BigAutoField(primary_key=True)

    username = models.CharField(
        max_length=255,
        unique=True,
    )

    password_hash = models.TextField()

    display_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    total_score = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
    )

    created_at = models.DateTimeField()

    @property
    def is_authenticated(self):
        return True

    class Meta:
        managed = False
        db_table = "users"


class UserSession(models.Model):
    session_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
    )

    status = models.CharField(
        max_length=20,
        default="idle",
    )

    current_match_id = models.BigIntegerField(
        null=True,
        blank=True,
    )

    last_heartbeat_at = models.DateTimeField(
        default=timezone.now,
    )

    created_at = models.DateTimeField(
        default=timezone.now,
    )

    updated_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        managed = False
        db_table = "sessions"
