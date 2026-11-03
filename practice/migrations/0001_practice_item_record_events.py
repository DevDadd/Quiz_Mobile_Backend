from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE TABLE IF NOT EXISTS practice_item_record_events ("
                "practice_id BIGINT NOT NULL, "
                "order_index INTEGER NOT NULL, "
                "recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "PRIMARY KEY (practice_id, order_index)"
                ")"
            ),
            reverse_sql="DROP TABLE IF EXISTS practice_item_record_events",
        ),
    ]
