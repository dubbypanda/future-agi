import { apiPath, assert } from "../lib/api-client.mjs";

export const publicApiJourneys = [
  {
    id: "MCP-OAUTH-001",
    title: "MCP public health and OAuth guard endpoints return JSON contracts",
    tags: ["mcp", "oauth", "public", "safe", "guard"],
    public: true,
    async run({ apiBase, evidence }) {
      const health = await request(apiBase, "GET", apiPath("/mcp/health/"));
      assertStatus(health, 200, "MCP health");
      assert(
        health.body?.status === true &&
          health.body?.result?.healthy === true &&
          Number.isFinite(Number(health.body?.result?.tool_count)),
        `MCP health payload mismatch: ${JSON.stringify(health.body)}`,
      );
      assertNoSensitiveTokens(health.body, "MCP health");

      const approveInfoMissing = await request(
        apiBase,
        "GET",
        apiPath("/mcp/oauth/approve-info/"),
      );
      assertStatus(approveInfoMissing, 400, "approve-info missing request_id");
      assertJsonError(
        approveInfoMissing,
        "Missing request_id",
        "approve-info missing request_id",
      );

      const approveInfoExpired = await request(
        apiBase,
        "GET",
        `${apiPath("/mcp/oauth/approve-info/")}?request_id=api-journey-missing`,
      );
      assertStatus(approveInfoExpired, 404, "approve-info expired request_id");
      assertJsonError(
        approveInfoExpired,
        "Approval request not found or expired",
        "approve-info expired request_id",
      );

      const authorizeMissing = await request(
        apiBase,
        "GET",
        apiPath("/mcp/oauth/authorize/"),
      );
      assertStatus(authorizeMissing, 400, "authorize missing parameters");
      assertJsonError(
        authorizeMissing,
        "Missing client_id or redirect_uri",
        "authorize missing parameters",
      );

      const authorizeUnsupported = await request(
        apiBase,
        "GET",
        `${apiPath("/mcp/oauth/authorize/")}?client_id=missing-client&redirect_uri=${encodeURIComponent(
          "https://example.com/callback",
        )}&response_type=token`,
      );
      assertStatus(
        authorizeUnsupported,
        400,
        "authorize unsupported response_type",
      );
      assertJsonError(
        authorizeUnsupported,
        "Unsupported response_type",
        "authorize unsupported response_type",
      );

      const authorizeUnknown = await request(
        apiBase,
        "GET",
        `${apiPath("/mcp/oauth/authorize/")}?client_id=missing-client&redirect_uri=${encodeURIComponent(
          "https://example.com/callback",
        )}&response_type=code`,
      );
      assertNoHtml500(authorizeUnknown, "authorize unknown client");
      assert(
        [400, 503].includes(authorizeUnknown.status),
        `authorize unknown client expected 400 or registry 503, saw ${authorizeUnknown.status}: ${formatBody(
          authorizeUnknown.body,
        )}`,
      );
      assertJsonError(
        authorizeUnknown,
        authorizeUnknown.status === 503
          ? "OAuth client registry unavailable"
          : "Unknown client_id",
        "authorize unknown client",
      );

      const tokenMissing = await request(
        apiBase,
        "POST",
        apiPath("/mcp/oauth/token/"),
        {},
      );
      assertStatus(tokenMissing, 400, "token missing fields");
      assertOAuthError(tokenMissing, "invalid_request", "token missing fields");
      assert(
        String(tokenMissing.body?.error_description || "").includes(
          "grant_type",
        ),
        `token missing fields did not mention grant_type: ${JSON.stringify(
          tokenMissing.body,
        )}`,
      );

      const tokenUnsupported = await request(
        apiBase,
        "POST",
        apiPath("/mcp/oauth/token/"),
        {
          grant_type: "client_credentials",
          client_id: "missing-client",
          client_secret: "secret",
        },
      );
      assertStatus(tokenUnsupported, 400, "token unsupported grant");
      assertOAuthError(
        tokenUnsupported,
        "unsupported_grant_type",
        "token unsupported grant",
      );

      const tokenUnknownClient = await request(
        apiBase,
        "POST",
        apiPath("/mcp/oauth/token/"),
        {
          grant_type: "authorization_code",
          code: "api-journey-missing-code",
          client_id: "missing-client",
          client_secret: "secret",
          redirect_uri: "https://example.com/callback",
        },
      );
      assertNoHtml500(tokenUnknownClient, "token unknown client");
      assert(
        [401, 503].includes(tokenUnknownClient.status),
        `token unknown client expected 401 or registry 503, saw ${tokenUnknownClient.status}: ${formatBody(
          tokenUnknownClient.body,
        )}`,
      );
      assertOAuthError(
        tokenUnknownClient,
        tokenUnknownClient.status === 503 ? "server_error" : "invalid_client",
        "token unknown client",
      );

      const approveUnauthenticated = await request(
        apiBase,
        "POST",
        apiPath("/mcp/oauth/approve/"),
        { request_id: "api-journey-missing", approved: false },
      );
      assert(
        [401, 403].includes(approveUnauthenticated.status),
        `approve unauthenticated expected 401/403, saw ${approveUnauthenticated.status}: ${formatBody(
          approveUnauthenticated.body,
        )}`,
      );
      assertJsonError(
        approveUnauthenticated,
        "Authentication credentials",
        "approve unauthenticated",
      );

      const consentUnauthenticated = await request(
        apiBase,
        "POST",
        apiPath("/mcp/oauth/consent/"),
        {
          client_id: "missing-client",
          redirect_uri: "https://example.com/callback",
          approved: false,
        },
      );
      assert(
        [401, 403].includes(consentUnauthenticated.status),
        `consent unauthenticated expected 401/403, saw ${consentUnauthenticated.status}: ${formatBody(
          consentUnauthenticated.body,
        )}`,
      );
      assertNoHtml500(consentUnauthenticated, "consent unauthenticated");

      evidence.push({
        health_tool_count: health.body.result.tool_count,
        approve_info_missing_status: approveInfoMissing.status,
        approve_info_expired_status: approveInfoExpired.status,
        authorize_unknown_status: authorizeUnknown.status,
        token_unknown_client_status: tokenUnknownClient.status,
        approve_unauthenticated_status: approveUnauthenticated.status,
        consent_unauthenticated_status: consentUnauthenticated.status,
      });
    },
  },
];

async function request(apiBase, method, pathName, body) {
  const response = await fetch(`${apiBase}${pathName}`, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const responseText = await response.text();
  return {
    status: response.status,
    body: parseBody(responseText),
    contentType: response.headers.get("content-type") || "",
  };
}

function parseBody(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function assertStatus(result, expectedStatus, label) {
  assert(
    result.status === expectedStatus,
    `${label} expected HTTP ${expectedStatus}, saw ${result.status}: ${formatBody(
      result.body,
    )}`,
  );
}

function assertNoHtml500(result, label) {
  assert(
    result.status !== 500 || !String(result.contentType).includes("text/html"),
    `${label} returned HTML 500 instead of a JSON API error.`,
  );
}

function assertJsonError(result, expectedText, label) {
  assert(
    result.body && typeof result.body === "object",
    `${label} returned non-JSON body: ${formatBody(result.body)}`,
  );
  const haystack = [
    result.body.error,
    result.body.detail,
    result.body.message,
    result.body.result,
  ]
    .filter(Boolean)
    .join(" ");
  assert(
    haystack.includes(expectedText),
    `${label} missing expected error text ${JSON.stringify(
      expectedText,
    )}: ${JSON.stringify(result.body)}`,
  );
}

function assertOAuthError(result, expectedError, label) {
  assert(
    result.body?.error === expectedError,
    `${label} expected OAuth error ${expectedError}, saw ${JSON.stringify(
      result.body,
    )}`,
  );
}

function assertNoSensitiveTokens(value, label) {
  const serialized = JSON.stringify(value || {});
  assert(
    !/(access_token|refresh_token|client_secret|Bearer\s+[A-Za-z0-9._-]+)/i.test(
      serialized,
    ),
    `${label} exposed token-like data: ${serialized}`,
  );
}

function formatBody(body) {
  if (typeof body === "string") return body.slice(0, 500);
  return JSON.stringify(body).slice(0, 500);
}
