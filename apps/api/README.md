# Logistics API

FastAPI service for the AI Fleet Cost Optimizer.

## Responsibilities

- Fleet and vehicle data
- Fuel transactions
- Mileage and utilization metrics
- Cost calculations
- Anomaly detection endpoints
- AI recommendations and route-plan lifecycle management

## Authentication and tenant context

Protected organization-scoped endpoints require an `Authorization: Bearer <token>` header. The API derives the user ID, organization ID, and role from a signed, short-lived token; client-supplied `X-Organization-ID`, `X-User-ID`, and `X-User-Role` headers are not used as authorization credentials.

Tokens are signed with HMAC-SHA256 and expire after `ACCESS_TOKEN_TTL_MINUTES` (default: 60). The `issue_access_token` helper is intended for trusted server-side identity/authentication code only; do not expose it as an unauthenticated public endpoint. A production identity flow should authenticate the user and authorize their organization membership before issuing a token.

Example environment configuration:

```bash
APP_ENV=production
ACCESS_TOKEN_SECRET=<at-least-32-character-random-secret>
ACCESS_TOKEN_TTL_MINUTES=60
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
```

Generate the signing secret using a cryptographically secure secret manager or generator. In production, application startup fails if the default development secret is used or the configured secret is shorter than 32 characters. Keep the secret out of source control and rotate it through a planned token invalidation process.

Example request:

```bash
curl -H "Authorization: Bearer <signed-token>" \
  https://<api-host>/api/v1/recommendations/<organization-uuid>
```

The public health endpoint is intended for service health checks. Organization creation and token issuance should be exposed only through a separately designed, rate-limited onboarding and identity flow before public production launch.

Organization creation is fail-closed unless `ORGANIZATION_PROVISIONING_TOKEN` is configured. A trusted provisioning caller must send it in the `X-Organization-Provisioning-Token` header. Keep this credential in a secret manager, restrict the route at the ingress/network layer, rotate the credential if exposed, and do not place it in browser code. This shared-secret gate is a bootstrap control, not a substitute for a complete, rate-limited onboarding and identity workflow.


## Recommendation execution and idempotency

Operational recommendation transitions that start a vehicle reassignment or shipment reroute must include an `Idempotency-Key` header. Use a new unpredictable or unique key for each logical request, and reuse the same key only when retrying that exact request.

```bash
curl -X PATCH \
  -H "Authorization: Bearer <signed-token>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: dispatch-change-<unique-request-id>" \
  -d '{"status":"in_progress","vehicle_id":"<replacement-vehicle-uuid>","expected_vehicle_id":"<currently-assigned-vehicle-uuid>"}' \
  https://<api-host>/api/v1/recommendations/actions/<action-uuid>/status
```

For an identical retry, the API returns the stored response without applying the transition again. Reusing a key with a different request body returns HTTP 409. Operational execution without the header returns HTTP 428. Vehicle reassignment also requires `expected_vehicle_id`, the vehicle assignment the operator reviewed; a stale expected assignment returns HTTP 409 instead of overwriting a newer dispatch decision. The action transition, operational database mutation, audit event, and idempotency response are committed in the same PostgreSQL transaction.

Apply database migrations in order for an existing installation:

1. `002_route_plans.sql`
2. `003_route_plan_invariants.sql`
3. `004_recommendation_action_events.sql`
4. `005_recommendation_action_idempotency.sql`
5. `006_tenant_relationship_integrity.sql`

Migration 006 adds database triggers that reject cross-organization relationships between trips, vehicles, and shipments; fuel transactions and their vehicles/trips; maintenance events and vehicles; alerts and their referenced records; recommendation actions and shipments; action events/idempotency records and their actions; and route plans and shipments. This protects data integrity even when writes bypass the API. Before production rollout, check existing data for cross-tenant relationships and repair any violations, then apply migrations in staging first.

The canonical bootstrap schema at `app/db/schema.sql` includes the current tables, but existing installations must apply migrations in order. Back up the database and test migrations against a staging copy before production rollout.

## Request observability

Every HTTP request receives an `X-Request-ID` response header. A caller-provided `X-Request-ID` is accepted only when it contains 1–128 ASCII letters, digits, dots, underscores, colons, or hyphens; otherwise the API generates a UUID. The ID is for correlation only and must never be treated as an authentication credential.

The API emits structured log records named `http_request_completed` with the request ID, method, path, HTTP status, and duration in milliseconds. Unhandled exceptions emit `http_request_failed` with the same correlation fields and a stack trace. Configure the deployment's log collector to parse these fields and retain logs under the organization's security and privacy policy. Do not add bearer tokens, request bodies, or other secrets to request logs.

Run the API observability tests with:

```bash
cd apps/api
PYTHONPATH=.:../.. pytest -q tests/test_request_observability.py
```

## Liveness and readiness probes

- `GET /health` is a liveness endpoint. It confirms the API process can respond and deliberately does not depend on PostgreSQL.
- `GET /ready` is a readiness endpoint. It executes `SELECT 1` against PostgreSQL and returns HTTP 200 only when the database is reachable; dependency failures return HTTP 503.

Configure container orchestration or the load balancer to use `/health` for liveness and `/ready` for readiness. Do not use a database-dependent readiness probe as the liveness probe, because a temporary database outage could otherwise trigger unnecessary API restarts.

