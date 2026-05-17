import structlog
from drf_yasg.utils import swagger_auto_schema
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from agentcc.models import AgentccOrgConfig
from agentcc.permissions import IsAdminToken
from agentcc.serializers.contracts import (
    AgentccErrorResponseSerializer,
    OrgConfigBulkResponseSerializer,
)
from agentcc.services.config_push import _build_payload
from tfc.utils.general_methods import GeneralMethods

logger = structlog.get_logger(__name__)


class OrgConfigBulkView(APIView):
    """
    Bulk endpoint for gateway startup sync.
    Returns all active org configs keyed by org ID.
    Authenticated by admin token (not user JWT).
    """

    authentication_classes = []
    permission_classes = [IsAdminToken]
    renderer_classes = [JSONRenderer]  # bypass camelCase — Go expects snake_case
    _gm = GeneralMethods()

    @swagger_auto_schema(
        responses={
            200: OrgConfigBulkResponseSerializer,
            400: AgentccErrorResponseSerializer,
        }
    )
    def get(self, request):
        try:
            configs = AgentccOrgConfig.no_workspace_objects.filter(
                is_active=True, deleted=False
            ).select_related("organization")

            result = {}
            for cfg in configs:
                org_id = str(cfg.organization_id)
                result[org_id] = _build_payload(org_id, cfg)

            return self._gm.success_response(result)
        except Exception as e:
            logger.exception("org_config_bulk_error", error=str(e))
            return self._gm.bad_request(str(e))
