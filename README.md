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

The migration directory is present under `apps/api/migrations`. `001_initial.sql` currently establishes migration tracking rather than replacing the canonical bootstrap schema. Existing databases should apply migrations in order; `002_route_plans.sql` adds route-plan persistence and `003_route_plan_invariants.sql` enforces its lifecycle and one-active-route invariant.

## API workflow

A typical operational decision flow is:

1. Create an organization.
2. Register vehicles and shipments.
3. Ingest or record trips and fuel/maintenance events.
4. Calculate fleet, corridor, and shipment risk.
5. Generate explainable recommendations.
6. Require an authorized operator to approve an executable recommendation.
7. Execute vehicle reassignment or select and activate a route plan.
8. Track the action through completion.

## Roles

| Role | Read | Approve / Execute |
| --- | --- | --- |
| `admin` | Yes | Yes |
| `operations_manager` | Yes | Yes |
| `fleet_manager` | Yes | Yes |
| `analyst` | Yes | No |
| `viewer` | Yes | No |

The current tenant context uses development headers. It is **not production authentication** and must be replaced with a real OAuth2/OIDC or equivalent asymmetric-token identity layer before production deployment.

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
- Replace development authentication with production identity management.
- Add production monitoring, structured logging, and error tracking.
- Expand country/currency/corridor configuration for African deployments.

Do not treat this repository as production-ready until those gates are completed.
