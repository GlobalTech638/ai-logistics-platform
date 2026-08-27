# Database

The MVP persistence layer uses PostgreSQL.

`schema.sql` defines the first multi-tenant tables:

- organizations
- vehicles
- fuel_transactions

The schema is intentionally country- and currency-aware for cross-border African logistics. Monetary values use PostgreSQL `NUMERIC`, not floating-point types.

The next persistence milestone is a SQLAlchemy repository layer and migrations.
