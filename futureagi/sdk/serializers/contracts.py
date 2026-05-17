from drf_yasg import openapi
from rest_framework import serializers

from sdk.serializers.analytics import (
    AnalyticsResponseSerializer,
    CallMetricsSerializer,
    CallRunDetailSerializer,
    ExecutionMetricsSerializer,
    ExecutionRunsSerializer,
)
from sdk.serializers.evaluations import ConfigureEvaluationsSerializer


class SDKErrorResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(required=False, allow_null=True)
    message = serializers.JSONField(required=False, allow_null=True)


class ConfigureEvaluationsRequestSerializer(serializers.Serializer):
    eval_config = ConfigureEvaluationsSerializer()
    platform = serializers.CharField()
    custom_eval_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    class Meta:
        ref_name = "SDKConfigureEvaluationsRequest"
        swagger_schema_fields = {
            "additional_properties": openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description="Provider-specific credential fields accepted at top level.",
            )
        }


class SDKMessageResultSerializer(serializers.Serializer):
    message = serializers.CharField()


class SDKConfigureEvaluationsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKMessageResultSerializer()


class SDKStandaloneEvalInputSerializer(serializers.Serializer):
    input = serializers.CharField(required=False, allow_blank=True)
    max_tokens = serializers.IntegerField(required=False, min_value=1)

    class Meta:
        ref_name = "SDKStandaloneEvalInput"
        swagger_schema_fields = {
            "additional_properties": openapi.Schema(type=openapi.TYPE_OBJECT)
        }


class SDKStandaloneEvalRequestSerializer(serializers.Serializer):
    inputs = SDKStandaloneEvalInputSerializer(many=True)
    config = serializers.DictField()
    protect_flash = serializers.BooleanField(required=False, default=False)


class SDKStandaloneEvalV2RequestSerializer(serializers.Serializer):
    eval_name = serializers.CharField()
    inputs = serializers.DictField()
    model = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    span_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    custom_eval_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    trace_eval = serializers.BooleanField(required=False, default=False)
    is_async = serializers.BooleanField(required=False, default=False)
    error_localizer = serializers.BooleanField(required=False, default=False)
    config = serializers.DictField(required=False)


class SDKStandaloneEvalResultItemSerializer(serializers.Serializer):
    evaluations = serializers.ListField(child=serializers.JSONField())


class SDKStandaloneEvalResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKStandaloneEvalResultItemSerializer(many=True)


class SDKStandaloneEvalV2QuerySerializer(serializers.Serializer):
    eval_id = serializers.UUIDField()


class SDKStandaloneEvalV2ResultSerializer(serializers.Serializer):
    eval_status = serializers.CharField()
    result = serializers.JSONField()


class SDKStandaloneEvalV2ResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKStandaloneEvalV2ResultSerializer()


class SDKEvalTemplateSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    organization = serializers.CharField(allow_blank=True, allow_null=True)
    owner = serializers.CharField(allow_blank=True, allow_null=True)
    eval_tags = serializers.JSONField(required=False, allow_null=True)
    config = serializers.JSONField(required=False, allow_null=True)
    eval_id = serializers.CharField(allow_blank=True, allow_null=True)
    criteria = serializers.JSONField(required=False, allow_null=True)
    choices = serializers.JSONField(required=False, allow_null=True)
    multi_choice = serializers.BooleanField(required=False, allow_null=True)


class SDKEvalTemplateResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKEvalTemplateSerializer()


class SDKGetEvalsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKEvalTemplateSerializer(many=True)


class SDKCICDEvaluationRunAcceptedSerializer(serializers.Serializer):
    message = serializers.CharField()
    project_name = serializers.CharField()
    version = serializers.CharField()
    evaluation_run_id = serializers.UUIDField()


class SDKCICDEvaluationRunSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    project = serializers.CharField()
    version = serializers.CharField()
    results_summary = serializers.DictField()


class SDKCICDEvaluationRunsResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    status = serializers.ChoiceField(choices=("processing", "completed"))
    evaluation_runs = SDKCICDEvaluationRunSummarySerializer(many=True, required=False)


class SDKCICDEvaluationRunAcceptedResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKCICDEvaluationRunAcceptedSerializer()


class SDKCICDEvaluationRunsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SDKCICDEvaluationRunsResultSerializer()


class SDKPaginatedExecutionMetricsResultSerializer(serializers.Serializer):
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    count = serializers.IntegerField()
    results = ExecutionMetricsSerializer(many=True)


class SDKPaginatedExecutionRunsResultSerializer(serializers.Serializer):
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    count = serializers.IntegerField()
    results = ExecutionRunsSerializer(many=True)


class SDKExecutionRunsDetailResultSerializer(ExecutionRunsSerializer):
    call_results = serializers.DictField(required=False)
    eval_explanation_summary = serializers.JSONField(required=False, allow_null=True)
    eval_explanation_summary_status = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class SDKSimulationMetricsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(
        help_text=(
            "CallMetrics, ExecutionMetrics, or paginated ExecutionMetrics depending "
            "on call_execution_id/execution_id/run_test_name query parameters."
        )
    )


class SDKSimulationRunsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(
        help_text=(
            "CallRunDetail, ExecutionRuns detail, or paginated ExecutionRuns depending "
            "on call_execution_id/execution_id/run_test_name query parameters."
        )
    )


class SDKSimulationAnalyticsNoCompletedSerializer(serializers.Serializer):
    run_test_name = serializers.CharField()
    message = serializers.CharField()
    eval_results = serializers.ListField(child=serializers.JSONField())
    eval_averages = serializers.DictField()
    system_summary = serializers.DictField()


class SDKSimulationAnalyticsResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(
        help_text=(
            "AnalyticsResponse when data exists, or a no-completed-executions result "
            "with run_test_name/message/eval_results/eval_averages/system_summary."
        )
    )


__all__ = [
    "AnalyticsResponseSerializer",
    "CallMetricsSerializer",
    "CallRunDetailSerializer",
    "ConfigureEvaluationsRequestSerializer",
    "SDKCICDEvaluationRunAcceptedResponseSerializer",
    "SDKCICDEvaluationRunsResponseSerializer",
    "SDKConfigureEvaluationsResponseSerializer",
    "SDKEvalTemplateResponseSerializer",
    "SDKErrorResponseSerializer",
    "SDKGetEvalsResponseSerializer",
    "SDKPaginatedExecutionMetricsResultSerializer",
    "SDKPaginatedExecutionRunsResultSerializer",
    "SDKSimulationAnalyticsResponseSerializer",
    "SDKSimulationMetricsResponseSerializer",
    "SDKSimulationRunsResponseSerializer",
    "SDKStandaloneEvalRequestSerializer",
    "SDKStandaloneEvalResponseSerializer",
    "SDKStandaloneEvalV2QuerySerializer",
    "SDKStandaloneEvalV2RequestSerializer",
    "SDKStandaloneEvalV2ResponseSerializer",
]
