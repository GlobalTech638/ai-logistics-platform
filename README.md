# Pan-African Logistics AI Platform

AI-powered logistics operations and fleet intelligence platform, designed for African logistics operators.

## Product

The MVP is an AI-first logistics Control Tower that turns operational data into prioritized decisions:

**Observe → Analyze → Detect → Explain → Recommend → Approve → Execute → Measure**

Core questions the platform is designed to answer:

1. How is my fleet performing?
2. What is going wrong now?
3. Which shipments are at risk?
4. Where am I losing money?
5. What should I do first?

## Current capabilities

- Multi-tenant organization scoping with development RBAC.
- Fleet health scoring from fuel, maintenance, and utilization signals.
- Fuel anomaly and estimated excess-cost analysis with currency awareness.
- Corridor risk and shipment risk scoring.
- Explainable rule-based recommendations.
- Recommendation action lifecycle: proposed → accepted → in_progress → completed.
- Vehicle reassignment execution with capacity, active-status, and trip-lock validation.
- Shipment rerouting through persisted route plans with one active route per shipment.
- Database-level route-plan lifecycle constraints and one-active-route invariant.
- Control Tower overview metrics and alert lifecycle management.
- Shipment SLA exception detection for missed pickups, overdue deliveries, and deliveries due within two hours.
- Completed-trip efficiency analytics using measured odometer distance, actual fuel consumption, and currency-separated fuel costs.
- Shipment revenue ledger with idempotent customer charge capture and currency-safe fuel contribution reporting.
- Append-only shipment timeline with migration backfill and recent delivered-shipment visibility.
- Responsive browser dashboard for operational review and action execution.

## Architecture

- `apps/api` — FastAPI backend, PostgreSQL access, domain services, and REST API.
- `apps/web` — Vite browser dashboard.
- `ai` — AI and decision-intelligence foundations.
- `services` — supporting domain/service foundations.
- `docs` — architecture and product documentation.

## Local development

### Backend

```bash
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

### PostgreSQL

The canonical bootstrap schema is `apps/api/app/db/schema.sql`.

Docker Compose is provided at the repository root:

```bash
docker compose up --build
```

The migration directory is present under `apps/api/migrations`. `001_initial.sql` currently establishes migration tracking rather than replacing the canonical bootstrap schema. Apply migrations in order after the canonical bootstrap schema: `002_route_plans.sql` adds route-plan persistence, `003_route_plan_invariants.sql` enforces route lifecycle and the one-active-route invariant, `004_recommendation_action_events.sql` adds action audit history, `005_recommendation_action_idempotency.sql` adds execution replay protection, `006_tenant_relationship_integrity.sql` enforces cross-tenant relationship integrity, `007_organization_memberships.sql` adds production membership and membership-audit storage, and `008_one_active_trip_per_vehicle.sql` enforces at most one unfinished trip per vehicle; `009_shipment_vehicle_assignments.sql` separates dispatch reservations from trip telemetry; `010_dispatch_assignment_idempotency.sql` adds replay protection for assignment commands; `011_dispatch_assignment_release_events.sql` adds append-only assignment audit events and release metadata; and `012_trip_execution_lifecycle.sql` adds trip start/completion measurements, audit events, and command idempotency; `013_shipment_timeline_events.sql` adds an append-only, tenant-checked shipment milestone ledger; `014_fuel_transaction_idempotency.sql` adds safe fuel receipt ingestion and fuel-recorded shipment milestones; `015_shipment_charges.sql` adds an immutable customer revenue ledger and idempotent charge capture. CI applies migrations 002-015 against PostgreSQL 16 and runs the integration suite.

## API workflow

A typical operational decision flow is:

1. Provision an organization with its initial owner subject; the owner receives an active admin membership.
2. Add operator memberships and assign least-privilege roles.
3. Register vehicles and shipments.
4. Rank eligible vehicles, reserve a vehicle for a pending shipment, and start the trip when the vehicle departs.
5. Record the end odometer to complete the trip; the API derives actual distance and elapsed duration, marks the shipment delivered, and releases the vehicle reservation.
6. Open the shipment timeline to review its creation, assignment, trip-start, and delivery milestones with actor and event details.
7. Record customer shipment charges and review currency-separated fuel contribution to identify underpriced or loss-making loads.
6. Ingest fuel/maintenance events and calculate fleet, corridor, and shipment risk.
6. Generate explainable recommendations.
7. Require an authorized operator to approve an executable recommendation.
8. Execute vehicle reassignment or select and activate a route plan.
9. Track the action through completion.

## Roles

| Role | Read | Approve / Execute |
| --- | --- | --- |
| `admin` | Yes | Yes |
| `operations_manager` | Yes | Yes |
| `fleet_manager` | Yes | Yes |
| `analyst` | Yes | No |
| `viewer` | Yes | No |

The API derives tenant identity and role from verified bearer-token claims. In development, tests and trusted local callers can use the short-lived HMAC token helper. In production (`APP_ENV=production`), that helper is disabled and the API accepts only identity-provider JWTs verified against the configured OIDC JWKS endpoint.

### Production identity configuration

Set these environment variables before starting the API:

| Variable | Purpose |
| --- | --- |
| `APP_ENV=production` | Enables production identity validation and disables local token issuance. |
| `OIDC_JWKS_URL` | HTTPS URL of the identity provider's JSON Web Key Set. |
| `OIDC_ISSUER` | Exact HTTPS issuer expected in the token's `iss` claim. |
| `OIDC_AUDIENCE` | API audience expected in the token's `aud` claim. |

The identity provider must issue RS256-signed access tokens containing `sub`, `exp`, `iat`, `iss`, `aud`, `organization_id`, and `organization_role`. The role claim must be one of `admin`, `operations_manager`, `fleet_manager`, `analyst`, or `viewer`. The organization claim must be a UUID. Tenant and role headers supplied by clients are not used for authorization.

Production authorization additionally requires the `organization_memberships` and `organization_membership_events` tables from migration `007_organization_memberships.sql`. Organization provisioning now requires an `owner_subject` and atomically creates that identity's initial active `admin` membership. Provision one active membership per user subject and organization before granting access. At request time, the API checks that membership is active and uses the database role as the authorization source of truth; a stale or elevated JWT role cannot override a downgraded database role. Missing, suspended, and revoked memberships are denied. Membership lifecycle changes therefore take effect on the next API request without waiting for access-token expiry.

Organization administrators can list members through `GET /api/v1/organizations/{organization_id}/members`, add members through `POST /api/v1/organizations/{organization_id}/members`, change roles or status through `PATCH /api/v1/organizations/{organization_id}/members/{user_subject}`, and inspect the audit trail through `GET /api/v1/organizations/{organization_id}/membership-events`. These endpoints are tenant-scoped and admin-only; mutations write membership audit events in the same transaction. The last active administrator cannot be demoted or suspended, and membership changes are serialized per organization to prevent concurrent removal of all administrators.

The OIDC integration validates the JWT signature using the configured JWKS, pins the accepted algorithm to RS256, and validates issuer, audience, expiry, and required claims. Configure the identity provider to issue short-lived access tokens and rotate signing keys through its JWKS. The identity provider authenticates the subject; the platform's membership database is authoritative for organization access and effective role. Provision and administer memberships through the protected organization provisioning and admin endpoints; never accept role or tenant selection from unverified client input.

Before production rollout, configure the identity provider's access-token claim mapping to this contract and verify key rotation, revocation/session termination behavior, MFA, account lifecycle, and organization membership changes. JWT signature verification alone does not provide immediate token revocation.

## Engineering principles

1. Build around measurable logistics ROI.
2. Keep recommendations explainable and auditable.
3. Separate deterministic business rules from probabilistic AI.
4. Require human approval before consequential operational actions.
5. Make operational state transitions explicit and transactional.
6. Design for Kenya/East Africa first, with country, currency, and corridor configuration suitable for later Pan-African expansion.

## Validation status

🚧 **v0.1 hardening phase.** The core decision loop and operational execution model are implemented. The remaining release gates are environment-level validation and production hardening, including:

- Run the complete backend test suite in a real build environment.
- Validate the PostgreSQL bootstrap/migration path against a clean and an existing database.
- Execute an end-to-end shipment → risk → recommendation → approval → execution → completion scenario.
- Complete production identity-provider onboarding, key rotation, session/revocation controls, MFA, and organization-membership provisioning and operational workflows.
- Add production monitoring, structured logging, and error tracking.
- Expand country/currency/corridor configuration for African deployments.

Do not treat this repository as production-ready until those gates are completed.

### HTTP observability and metrics

- `GET /health` is a liveness probe and does not require PostgreSQL.
- `GET /ready` is a readiness probe and returns `503` when the database check fails.
- Every response includes an `X-Request-ID`; a valid caller-supplied ID is preserved, otherwise the API generates one. Completion logs include request ID, method, route path, status code, and duration.
- `GET /metrics` exposes Prometheus text-format request counters and duration sums/counts by HTTP method, route template, and status class. Route templates are used rather than raw URL paths to avoid shipment/action IDs creating unbounded metric cardinality.

**Deployment note:** these metrics are process-local. With multiple workers or replicas, scrape each process where possible or aggregate in a monitoring layer; do not interpret one process's counters as fleet-wide totals. Restrict the metrics endpoint to trusted monitoring infrastructure at the ingress/network layer.
