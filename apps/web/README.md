# Logistics Control Tower Web

Vite browser dashboard for fleet intelligence and dispatch operations.

## Local setup

1. Start PostgreSQL and the API using the repository root README.
2. Copy `runtime-settings.example.js` to `runtime-settings.js`.
3. Configure the API URL, organization ID, user subject, role, and a valid short-lived bearer access token in `runtime-settings.js`.
4. Install dependencies and start the dashboard:

```bash
npm install
npm run dev
```

The local `runtime-settings.js` file is ignored by Git. Never commit credentials or production tokens.

## Runtime settings

The example file exposes these browser settings:

- `LOGISTICS_API_URL`: API origin, e.g. `http://localhost:8000`.
- `LOGISTICS_ORGANIZATION_ID`: organization UUID.
- `LOGISTICS_USER_ID`: informational local user subject.
- `LOGISTICS_USER_ROLE`: presentation role; the API remains authoritative.
- `LOGISTICS_ACCESS_TOKEN`: short-lived signed access token.

The dashboard sends the bearer token with API requests. The user ID and role settings are not authorization credentials; verified token claims and current database membership determine access. Do not place long-lived secrets in browser assets.

Production deployments must integrate the organization's OIDC login/session flow and inject short-lived access tokens at runtime. The dashboard does not yet provide a hosted sign-in screen or token refresh workflow.

## Dispatch and trip execution

The dispatch panel supports:
- Pending shipment readiness and global queue summaries.
- Eligible vehicle ranking and vehicle reservation.
- Operator-entered planned distance, planned duration, and start odometer to start a trip.
- Active trip visibility.
- Trip completion using the end odometer; the API calculates measured distance and elapsed duration, marks the shipment delivered, and releases the vehicle.

The API enforces authorization, tenant isolation, vehicle capacity, active reservations, state transitions, and idempotent command handling. Browser-side role settings only control which controls are shown; they do not grant permission.
