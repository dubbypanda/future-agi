"""Backfill is_default=True on the highest-numbered version for templates where no version carries the flag."""

import logging

from django.db import migrations, models


def backfill_is_default(apps, schema_editor):
    EvalTemplate = apps.get_model("model_hub", "EvalTemplate")
    EvalTemplateVersion = apps.get_model("model_hub", "EvalTemplateVersion")

    templates_needing_fix = (
        EvalTemplate.objects.filter(deleted=False, versions__deleted=False)
        .annotate(
            default_count=models.Count(
                "versions", filter=models.Q(versions__is_default=True, versions__deleted=False)
            ),
        )
        .filter(default_count=0)
        .distinct()
    )

    fixed = 0
    for template in templates_needing_fix.iterator():
        latest = (
            EvalTemplateVersion.objects.filter(
                eval_template=template, deleted=False
            )
            .order_by("-version_number")
            .first()
        )
        if latest is None:
            continue
        latest.is_default = True
        latest.save(update_fields=["is_default"])
        fixed += 1

    if fixed:
        logging.getLogger(__name__).info(
            "Backfilled is_default=True on latest version for %d templates.", fixed
        )


class Migration(migrations.Migration):
    dependencies = [
        ("model_hub", "0112_eval_ground_truth_tenant_scope"),
    ]

    operations = [
        migrations.RunPython(backfill_is_default, reverse_code=migrations.RunPython.noop),
    ]
