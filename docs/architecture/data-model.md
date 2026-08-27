# Data Model

The initial domain model is designed for multi-country African operations.

## Organization

The tenant boundary. Stores the operating country and default currency.

## Vehicle

A fleet asset belonging to an organization. Fuel-efficiency expectations are vehicle-specific rather than globally assumed.

## FuelTransaction

A fuel purchase linked to a vehicle and organization. Each transaction stores currency and country explicitly so the platform can support cross-border operations.

## Design rules

- Use UUIDs for domain identifiers.
- Store monetary values with decimal precision.
- Never infer currency from a country at the business-logic layer.
- Preserve transaction country because vehicles may cross borders.
- Keep expected fuel efficiency at vehicle/configuration level.
- The future persistence layer will use PostgreSQL + PostGIS.
