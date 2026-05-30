"""OTel ingestion → ObservationSpan write path.

CH25-TODO: KEEP-PG. This entire module is the OTel ingest write
endpoint — every ObservationSpan.objects.create() / Trace.objects.get/
create is a dual-write source-of-truth operation (D-027). CH receives
the row via PeerDB CDC after the PG transaction commits. There is no
CH-write path by design; CHSpanReader cannot be applied here.
"""

import structlog
from django.db import IntegrityError, transaction

from model_hub.models.prompt_label import PromptLabel
from model_hub.models.run_prompt import PromptVersion
from tracer.models.observation_span import EndUser, ObservationSpan
from tracer.models.project import Project
from tracer.models.trace import Trace
from tracer.models.trace_session import TraceSession
from tracer.utils.helper import get_default_project_session_config
from tracer.utils.otel import convert_otel_span_to_observation_span

logger = structlog.get_logger(__name__)


def create_single_otel_span(data, organization_id, user_id, workspace_id=None):
    parsed_data = convert_otel_span_to_observation_span(
        data, organization_id, user_id, workspace_id
    )

    trace_manager = getattr(Trace, "no_workspace_objects", Trace.objects)
    existing_trace = trace_manager.filter(id=parsed_data["trace"]).first()
    if existing_trace and existing_trace.project_id != parsed_data["project"].id:
        raise ValueError("Trace does not belong to the resolved project")

    try:
        trace = Trace.objects.get(
            id=parsed_data["trace"], project=parsed_data["project"]
        )
    except Trace.DoesNotExist:
        try:
            trace, created = Trace.objects.get_or_create(
                id=parsed_data["trace"],
                defaults={
                    "project": parsed_data["project"],
                    **(
                        {"project_version": parsed_data["project_version"]}
                        if parsed_data["project_type"] == "experiment"
                        else {}
                    ),
                },
            )

        except Exception as e:
            logger.exception(f"{e}")
            raise Exception(  # noqa: B904
                "Error creating trace while creating observation span from otel"
            )

    val = parsed_data["observation_span"]
    val["trace"] = trace

    if parsed_data.get("end_user"):
        end_user_data = parsed_data["end_user"]
        defaults_fields = ["user_id_type", "user_id_hash", "metadata"]
        defaults = {key: end_user_data.get(key) for key in defaults_fields}
        defaults["metadata"] = defaults.get("metadata", {})
        if (
            end_user_data.get("user_id") is not None
            and parsed_data["project"].trace_type == "observe"
        ):
            try:
                with transaction.atomic():
                    # Try to get or create the EndUser
                    end_user, created = EndUser.objects.get_or_create(
                        user_id=end_user_data["user_id"],
                        organization_id=organization_id,
                        project=trace.project,
                        user_id_type=end_user_data.get("user_id_type"),
                        defaults=defaults,
                    )
            except IntegrityError:
                # Another thread/process created the record first
                end_user = EndUser.objects.get(
                    user_id=end_user_data["user_id"],
                    organization_id=organization_id,
                    project=parsed_data["project"],
                    user_id_type=end_user_data.get("user_id_type"),
                )

            val["end_user"] = end_user

    if (
        parsed_data["prompt_details"] is not None
        and val.get("observation_type", None) == "llm"
    ):
        prompt_details = parsed_data["prompt_details"]
        prompt_template_name = prompt_details.get("prompt_template_name", None)
        prompt_template_version = prompt_details.get("prompt_template_version", None)
        prompt_template_label = prompt_details.get("prompt_template_label", None)

        if prompt_template_name and prompt_template_label:
            filters = {
                "original_template__name": prompt_template_name,
                "original_template__organization": organization_id,
                "labels__name": prompt_template_label,
            }

            if prompt_template_version:
                filters["template_version"] = prompt_template_version

            prompt_version = PromptVersion.objects.filter(**filters).first()

            if prompt_version:
                prompt_labels_ids = prompt_version.labels.through.objects.filter(
                    promptversion_id=prompt_version
                ).values_list("promptlabel_id", flat=True)
                req_label = None
                if prompt_labels_ids:
                    req_label = PromptLabel.no_workspace_objects.filter(
                        id__in=prompt_labels_ids, name=prompt_template_label
                    ).first()

                if req_label:
                    val["prompt_version"] = prompt_version
                    val["prompt_label_id"] = str(req_label.id)

    observation_span = ObservationSpan.objects.create(**val)

    if not observation_span:
        raise ValueError("observation_span is None")

    if not observation_span.project:
        raise ValueError(f"Project is None for observation_span {observation_span}")

    if not observation_span.trace:
        raise ValueError(f"Trace is None for observation_span {observation_span}")

    # Update trace with input/output from root span
    if observation_span.parent_span_id is None:
        attrs = val.get("span_attributes") or val.get("eval_attributes") or {}
        input_val = getattr(observation_span, "input", None) or attrs.get("input.value")
        output_val = getattr(observation_span, "output", None) or attrs.get(
            "output.value"
        )
        if input_val:
            trace.input = input_val
        if output_val:
            trace.output = output_val
    trace.save()

    trace_session = None
    if parsed_data["session_name"] is not None:
        try:
            trace_session = TraceSession.objects.get(
                name=parsed_data["session_name"], project=observation_span.project
            )
            trace.session = trace_session
            trace.save()
        except TraceSession.DoesNotExist:
            try:
                project = Project.objects.get(id=observation_span.project.id)
                trace_session = TraceSession.objects.create(
                    name=parsed_data["session_name"],
                    project=project,
                )
                trace.session = trace_session
                project.session_config = get_default_project_session_config()
                project.save()
                trace.save()
            except Exception as e:
                logger.exception(f"{e}")
                raise Exception(  # noqa: B904
                    "Error creating trace session while creating observation span from otel"
                )

        except Exception as e:
            logger.exception(f"{e}")
            raise Exception(  # noqa: B904
                "Error creating trace while creating observation span from otel"
            )

    # CH25: mirror the trace into the CH `traces` table (the app-level
    # replacement for the removed PeerDB CDC path that fed trace_dict). Gate on
    # the ROOT span — it carries the trace's identity + input/output, so this
    # fires ~once per trace instead of once per span. Post-commit + best-effort
    # so a CH hiccup never breaks PG ingestion.
    if observation_span.parent_span_id is None:
        from tracer.services.clickhouse.v2.trace_writer import (
            mirror_traces_to_clickhouse,
        )

        transaction.on_commit(
            lambda tid=str(trace.id): mirror_traces_to_clickhouse([tid])
        )

        # CH25 (P3a): mirror the curated EndUser / TraceSession resolved above
        # (val["end_user"] set ~L90, trace.session set ~L157/166) into CH
        # `end_users` / `trace_sessions` — alongside (NOT replacing) the PG
        # get_or_create, which stays the id source until P3b. Gated on the ROOT
        # span like the trace mirror so it fires ~once per trace, not per span;
        # post-commit + best-effort so a CH hiccup never breaks ingestion.
        # Reference the locally-resolved objects (val["end_user"], trace_session)
        # — NOT trace.session, whose FK descriptor would lazy-fetch a PG row when
        # session_name was absent (the hot-path round-trip this migration avoids).
        _ch_end_user = val.get("end_user")
        _ch_session = trace_session
        if _ch_end_user is not None or _ch_session is not None:
            from tracer.services.clickhouse.v2.curated_writer import (
                mirror_curated_dimensions_to_clickhouse,
            )

            transaction.on_commit(
                lambda eu=_ch_end_user, s=_ch_session: (
                    mirror_curated_dimensions_to_clickhouse(
                        [eu] if eu is not None else None,
                        [s] if s is not None else None,
                    )
                )
            )

    return observation_span
