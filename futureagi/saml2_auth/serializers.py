from rest_framework import serializers

from saml2_auth.models import SAMLMetadataModel


class SAMLSerializer(serializers.ModelSerializer):
    class Meta:
        model = SAMLMetadataModel
        fields = ("name", "id", "identity_type", "is_enabled")
        read_only_fields = (
            "id",
            "identity_type",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return attrs


class SAMLErrorResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.JSONField(required=False, allow_null=True)
    message = serializers.JSONField(required=False, allow_null=True)


class SAMLUrlResultSerializer(serializers.Serializer):
    url = serializers.URLField()


class SAMLUrlResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = SAMLUrlResultSerializer()


class SAMLStringResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    result = serializers.CharField()


class SAMLIDPLoginQuerySerializer(serializers.Serializer):
    email = serializers.EmailField()
    next = serializers.CharField(required=False, allow_blank=True)


class SAMLAuthLoginQuerySerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("google", "github", "microsoft"))


class SAMLOAuthCallbackQuerySerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True)
