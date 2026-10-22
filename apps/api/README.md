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


## Recommendation execution and idempotency

Operational recommendation transitions that start a vehicle reassignment or shipment reroute must include an `Idempotency-Key` header. Use a new unpredictable or unique key for each logical request, and reuse the same key only when retrying that exact request.

```bash
curl -X PATCH \
  -H "Authorization: Bearer <signed-token>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: dispatch-change-<unique-request-id>" \
  -d '{"status":"in_progress","vehicle_id":"<vehicle-uuid>"}' \
  https://<api-host>/api/v1/recommendations/actions/<action-uuid>/status
```

For an identical retry, the API returns the stored response without applying the transition again. Reusing a key with a different request body returns HTTP 409. Operational execution without the header returns HTTP 428. The action transition, operational database mutation, audit event, and idempotency response are committed in the same PostgreSQL transaction.

Apply database migrations in order for an existing installation:

1. `002_route_plans.sql`
2. `003_route_plan_invariants.sql`
3. `004_recommendation_action_events.sql`
4. `005_recommendation_action_idempotency.sql`

The canonical bootstrap schema at `app/db/schema.sql` includes the current tables. Back up the database and test migrations against a staging copy before production rollout.
