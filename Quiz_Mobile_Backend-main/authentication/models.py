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

class Challenge(models.Model):
    challenge_id = models.BigAutoField(primary_key=True)
    challenger = models.ForeignKey(User, on_delete=models.CASCADE, related_name='challenges_sent', db_column='challenger_id')
    opponent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='challenges_received', db_column='opponent_id')
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    match_id = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'challenges'

class MatchParticipant(models.Model):
    # Django không hỗ trợ khóa chính kép mặc định, ta tạm dùng match_id làm PK để SELECT dữ liệu
    match_id = models.BigIntegerField(primary_key=True) 
    side = models.CharField(max_length=10)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, db_column='user_id')
    result = models.CharField(max_length=10)
    points_earned = models.DecimalField(max_digits=3, decimal_places=1)
    correct_count = models.SmallIntegerField(default=0)
    duration_seconds = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = 'match_participants'
