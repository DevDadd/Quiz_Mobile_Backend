from django.core.management.base import BaseCommand
from django.db import connection

from matches.services import resolve_if_expired


class Command(BaseCommand):
    """Dọn các trận running mà không ai poll nên chưa được lazy-resolve.

    Chạy định kỳ (khuyến nghị mỗi 5s) qua scheduler ngoài (cron/Task Scheduler/
    Render Cron Job) vì project chưa có Celery/worker nào sẵn:
        python manage.py cleanup_stale_matches
    """

    help = "Tự động submit + finalize các trận đã hết giờ mà không client nào poll."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT match_id FROM matches
                WHERE status = 'ongoing'
                AND started_at + time_limit_seconds * interval '1 second' < now() - interval '3 seconds'
                """
            )
            stale_ids = [row[0] for row in cursor.fetchall()]

        for match_id in stale_ids:
            resolve_if_expired(match_id)

        self.stdout.write(self.style.SUCCESS(f"Đã dọn {len(stale_ids)} trận treo."))
