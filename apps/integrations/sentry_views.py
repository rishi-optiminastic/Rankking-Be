"""The Sentry webhook endpoint. See ``sentry_bridge`` for what it does and why."""

from __future__ import annotations

import json
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .sentry_bridge import RESOURCE_HEADER, SIGNATURE_HEADER, handle_issue_created, verify_signature

logger = logging.getLogger("apps")


class SentryWebhookView(APIView):
    """POST /api/integrations/sentry/webhook/ — file new Sentry issues on GitHub.

    Unauthenticated by necessity (Sentry cannot log in) but not unguarded: the
    HMAC signature is the gate, and it is checked against the raw body before the
    payload is parsed.
    """

    permission_classes = [AllowAny]
    # Sentry has no way to retry on a schedule that respects our throttles, and a
    # 429 here silently loses an alert. The signature is the real gate.
    throttle_classes = []

    def post(self, request):
        if not verify_signature(request.body, request.headers.get(SIGNATURE_HEADER, "")):
            # Identical response whether the secret is unset, missing or wrong:
            # a prober should not learn which.
            logger.warning("sentry webhook: rejected an unsigned or mis-signed request")
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        resource = (request.headers.get(RESOURCE_HEADER) or "").strip()
        action = (payload.get("action") or "").strip()
        if resource != "issue" or action != "created":
            # Sentry sends installation/comment/metric-alert hooks down the same
            # URL; acknowledge them so it does not retry, and do nothing.
            return Response(status=status.HTTP_202_ACCEPTED)

        try:
            url = handle_issue_created(payload)
        except Exception:
            # Never 500 at Sentry: it retries, and a retry would file a duplicate
            # issue. The bridge logs the detail.
            logger.exception("sentry webhook: could not file a GitHub issue")
            return Response(status=status.HTTP_202_ACCEPTED)

        return Response({"github_issue": url} if url else {}, status=status.HTTP_200_OK)
