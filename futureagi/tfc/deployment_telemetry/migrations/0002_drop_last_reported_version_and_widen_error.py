from django.db import migrations, models


class Migration(migrations.Migration):
    """Drop the unused ``last_reported_version`` column and widen
    ``last_registration_error`` from CharField(100) to TextField.

    Round-5 review on PR #891 flagged that ``last_reported_version`` is
    written in two places but read nowhere, and that the 100-char cap on
    ``last_registration_error`` truncates ``HTTPSConnectionPool`` /
    ``ConnectionError`` messages mid-stack so the diagnostic field becomes
    diagnostically useless. This migration removes the dead column and
    widens the error field; the writer/reader side was already updated in
    the same commit.
    """

    dependencies = [
        ("deployment_telemetry", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="DeploymentTelemetryState",
            name="last_reported_version",
        ),
        migrations.AlterField(
            model_name="DeploymentTelemetryState",
            name="last_registration_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
