from rest_framework import serializers


class IntegrationErrorResponseSerializer(serializers.Serializer):
    """Integration API error envelope."""

    status = serializers.BooleanField(default=False)
    result = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    error = serializers.CharField(required=False, allow_blank=True, allow_null=True)


INTEGRATION_ERROR_RESPONSES = {
    400: IntegrationErrorResponseSerializer,
    404: IntegrationErrorResponseSerializer,
    500: IntegrationErrorResponseSerializer,
}

INTEGRATION_SYNC_ERROR_RESPONSES = {
    **INTEGRATION_ERROR_RESPONSES,
    409: IntegrationErrorResponseSerializer,
}
