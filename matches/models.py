from django.db import models

from authentication.models import User


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
    # PK thật là (match_id, side). Django không hỗ trợ khóa chính kép mặc định,
    # ta tạm dùng match_id làm PK để SELECT dữ liệu qua ORM khi cần.
    # Mọi ghi/sửa thực tế trên bảng này (2 dòng cùng match_id) đi qua raw SQL trong matches.services.
    match_id = models.BigIntegerField(primary_key=True)
    side = models.CharField(max_length=10)  # enum player_side_enum: P1 | P2
    user = models.ForeignKey(User, on_delete=models.RESTRICT, db_column='user_id', null=True, blank=True)
    result = models.CharField(max_length=10)  # enum match_result_enum: win | lose | draw
    points_earned = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    correct_count = models.SmallIntegerField(default=0)
    duration_seconds = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'match_participants'
