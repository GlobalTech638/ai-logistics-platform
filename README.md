# AI Logistics Platform

AI-powered logistics operations and fleet cost optimization platform.

## MVP: AI Fleet Cost Optimizer

The first product focuses on identifying fleet cost leaks through fuel-efficiency analysis, mileage normalization, anomaly detection, and actionable recommendations.

### Product loop

**Observe → Analyze → Detect → Explain → Recommend → Measure**

### Initial architecture

- `apps/web` — Next.js operations dashboard
- `apps/api` — FastAPI backend
- `ai` — anomaly detection, forecasting, and decision intelligence
- `services` — fleet, fuel, routing, alerts, and forecasting domains
- `packages` — shared contracts and database layer
- `docs` — architecture and product documentation

## Development principles

1. Build around measurable logistics ROI.
2. Keep AI recommendations explainable and auditable.
3. Separate deterministic business rules from probabilistic AI.
4. Require human approval before consequential operational actions in the MVP.
5. Treat historical operational data and outcomes as a long-term product moat.

## Status

🚧 Early MVP — architecture and domain foundations.
