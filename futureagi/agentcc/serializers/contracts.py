from rest_framework import serializers


class AgentccErrorResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_blank=True)
    message = serializers.JSONField(required=False, allow_null=True)


class AgentccEmptyRequestSerializer(serializers.Serializer):
    pass


class AgentccJSONResultResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField()


class AgentccListResultResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.ListField(child=serializers.JSONField())


class GatewayListResponseSerializer(AgentccListResultResponseSerializer):
    pass


class GatewayDetailResponseSerializer(AgentccJSONResultResponseSerializer):
    pass


class GatewayHealthResponseSerializer(AgentccJSONResultResponseSerializer):
    pass


class GatewayConfigResponseSerializer(AgentccJSONResultResponseSerializer):
    pass


class GatewayMutationResultSerializer(serializers.Serializer):
    status = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False)
    gateway_synced = serializers.BooleanField(required=False)
    gateway_warning = serializers.CharField(required=False, allow_blank=True)
    action = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    guardrail = serializers.CharField(required=False, allow_blank=True)
    budget = serializers.CharField(required=False, allow_blank=True)
    server = serializers.CharField(required=False, allow_blank=True)
    enabled = serializers.BooleanField(required=False)


class GatewayMutationResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = GatewayMutationResultSerializer()


class GatewayConfigPatchRequestSerializer(serializers.Serializer):
    guardrails = serializers.DictField(required=False)
    routing = serializers.DictField(required=False)
    cache = serializers.DictField(required=False)
    rate_limiting = serializers.DictField(required=False)
    budgets = serializers.DictField(required=False)
    cost_tracking = serializers.DictField(required=False)
    ip_acl = serializers.DictField(required=False)
    alerting = serializers.DictField(required=False)
    privacy = serializers.DictField(required=False)
    tool_policy = serializers.DictField(required=False)
    mcp = serializers.DictField(required=False)
    a2a = serializers.DictField(required=False)
    audit = serializers.DictField(required=False)
    model_database = serializers.DictField(required=False)
    model_map = serializers.DictField(required=False)


class GatewayProviderUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    config = serializers.DictField()


class GatewayNameRequestSerializer(serializers.Serializer):
    name = serializers.CharField()


class GatewayToggleGuardrailRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    enabled = serializers.BooleanField()


class GatewayNamedConfigRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    config = serializers.DictField()


class GatewayPlaygroundTestRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField()
    model = serializers.CharField(required=False, allow_blank=True)
    system_prompt = serializers.CharField(required=False, allow_blank=True)


class GatewayBudgetSetRequestSerializer(serializers.Serializer):
    level = serializers.CharField()
    config = serializers.DictField()


class GatewayBudgetRemoveRequestSerializer(serializers.Serializer):
    level = serializers.CharField()


class GatewayBatchSubmitRequestSerializer(serializers.Serializer):
    requests = serializers.ListField(child=serializers.DictField())
    max_concurrency = serializers.IntegerField(required=False, min_value=1, default=5)


class GatewayBatchRequestSerializer(serializers.Serializer):
    batch_id = serializers.CharField()


class GatewayMCPServerUpdateRequestSerializer(serializers.Serializer):
    server_id = serializers.CharField()
    config = serializers.DictField()


class GatewayMCPServerRemoveRequestSerializer(serializers.Serializer):
    server_id = serializers.CharField()


class GatewayMCPGuardrailsUpdateRequestSerializer(serializers.Serializer):
    config = serializers.DictField()


class GatewayMCPToolTestRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    arguments = serializers.DictField(required=False, default=dict)


class PIIEntitySerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    category = serializers.CharField()


class PIIEntitiesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = PIIEntitySerializer(many=True)


class TopicCategorySerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    subcategories = serializers.ListField(child=serializers.CharField())


class TopicCategoriesResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = TopicCategorySerializer(many=True)


class ValidateCELRequestSerializer(serializers.Serializer):
    expression = serializers.CharField()


class ValidateCELResultSerializer(serializers.Serializer):
    expression = serializers.CharField()
    valid = serializers.BooleanField()
    error = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class ValidateCELResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = ValidateCELResultSerializer()


class WebhookLogsRequestSerializer(serializers.Serializer):
    logs = serializers.ListField(child=serializers.DictField(), required=False)


class ShadowResultsWebhookRequestSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField(), required=False)


class WebhookIngestResultSerializer(serializers.Serializer):
    ingested = serializers.IntegerField()


class WebhookIngestResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = WebhookIngestResultSerializer()


class APIKeyBulkItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    owner = serializers.CharField(allow_blank=True)
    key_hash = serializers.CharField()
    models = serializers.ListField(child=serializers.CharField())
    providers = serializers.ListField(child=serializers.CharField())
    metadata = serializers.DictField()


class APIKeyBulkResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = APIKeyBulkItemSerializer(many=True)


class OrgConfigBulkResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.DictField()


class SpendSummaryQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(
        choices=("daily", "weekly", "monthly", "total"), required=False
    )


class SpendSummaryResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.DictField()
