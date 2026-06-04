"""Add pinned_version FK to UserEvalMetric.

Allows each dataset/module eval binding to pin to a specific
EvalTemplateVersion for runtime resolution. NULL means "use
default version or live template" (backward compatible).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("model_hub", "0106_decouple_telemetry_fk_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="userevalmetric",
            name="pinned_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pinned_user_metrics",
                to="model_hub.evaltemplateversion",
                help_text="Pin to a specific template version for runtime.",
            ),
        ),
    ]
