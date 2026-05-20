from functools import wraps

import structlog
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse

from tfc.utils.api_errors import build_error_envelope

logger = structlog.get_logger(__name__)


def check_db_connection():
    """Check if database connections are alive"""
    for db_name in connections:
        try:
            c = connections[db_name].cursor()
            c.execute("SELECT 1")
            c.fetchone()
            c.close()
        except OperationalError as e:
            logger.error(f"Database {db_name} connection failed: {str(e)}")
            return False
    return True


def db_connection_required(view_func):
    """Decorator to check DB connection before view execution"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not check_db_connection():
            return JsonResponse(
                build_error_envelope(
                    "Database connection error",
                    status_code=503,
                    code="service_unavailable",
                ),
                status=503,
            )
        return view_func(request, *args, **kwargs)

    return wrapper
