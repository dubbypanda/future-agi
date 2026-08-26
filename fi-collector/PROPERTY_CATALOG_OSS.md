# Unified property catalog: OSS/local compatibility

This page defines the authoritative non-EE setup for the unified property
catalog. It is a development and qualification path, not part of the normal
one-command self-host startup.

## Keep the two catalog paths separate

| Path | Producer switch | Consumer | Purpose |
| --- | --- | --- | --- |
| Unified property catalog | `FI_PROPERTY_CATALOG_MODE` | `fi-property-catalog-consumer` | System, eval, annotation, dataset, simulation, and span-attribute properties |
| Legacy span attributes | `FI_CATALOG_MODE` | `fi-catalog-consumer` | Pre-release span-attribute-only catalog |

Never enable both switches in one collector. The topic initializer in
`docker-compose.catalog-kafka.dev.yml` belongs only to the legacy path and is
profile-gated. A unified deployment uses a new deployment-scoped topic such as
`futureagi.dev.property-catalog.<deployment_id>`.

## Authoritative local arrangement

There are two deliberate states:

1. The root `docker-compose.yml` is the authoritative OSS baseline. It provides
   PostgreSQL, ClickHouse, Redis, the backend, and `fi-collector`, but it has no
   Kafka service or `fi-property-catalog-consumer`. The collector sets both
   catalog producer modes to `disabled`; the backend sets
   `PROPERTY_CATALOG_READ_MODE=off` and
   `PROPERTY_CATALOG_DEV_RECONCILE_ENABLED=false`.
2. The only full end-to-end qualification path is the checked-in
   [`deploy/dev/property-catalog-docker` bundle](../deploy/dev/property-catalog-docker/README.md).
   Despite its directory name, its catalog implementation is OSS-owned: it
   runs the Go producer and consumer from `fi-collector/` and the Python
   catalog code under
   `futureagi/tracer/services/clickhouse/v2/property_catalog/`. It does not
   import `ee.*`.

Do not create a second shortcut Compose stack. The qualification bundle is
intentionally responsible for the dedicated topic, isolated target database,
separate least-privilege ClickHouse identities, revision fence, durable spool,
and exact workspace allowlist. Bypassing those gates can make containers look
healthy while silently rejecting hot admission.

## Data flow and ownership

| Component | Role |
| --- | --- |
| PostgreSQL | Authoritative relational sources for eval templates/configs, simulation eval configs, annotation labels, and dataset columns |
| Source ClickHouse | Authoritative spans and historical span attributes |
| Python reconciler/operator | Opens a bounded `building` revision, projects relational and historical span definitions/values, writes control evidence, and publishes the revision fence |
| `fi-collector` | Produces live span-attribute value envelopes only while an allowlisted revision fence accepts hot admission |
| Kafka | Dedicated transport for unified hot envelopes; it is not the legacy topic |
| `fi-property-catalog-consumer` | Validates sequence and lease evidence, then writes catalog data and the delivery ledger |
| Isolated ClickHouse catalog | Six additive tables: definitions, attribute values, checkpoints, activations, deliveries, and source streams |
| Backend definition/value APIs | Remain off until an explicit admitted `shadow` or `read` configuration targets the isolated catalog |

Relational changes are reflected by the next successful reconcile, not by the
Go hot path. New span attributes use the Kafka path while the revision is
`building`; activation makes the completed revision visible to definition and
value readers.

## Repository-local verification

Run these commands from the repository root. They do not contact production.

Confirm the OSS Compose contract:

```bash
docker compose -f docker-compose.yml config --services
docker compose -f docker-compose.yml config --format json > /tmp/futureagi-oss-compose.json
python3 -c 'import json; d=json.load(open("/tmp/futureagi-oss-compose.json")); s=d["services"]; print({"postgres": "postgres" in s, "clickhouse": "clickhouse" in s, "kafka": "kafka" in s, "unified_consumer": "fi-property-catalog-consumer" in s, "producer_mode": s["fi-collector"]["environment"].get("FI_PROPERTY_CATALOG_MODE"), "read_mode": s["backend"]["environment"].get("PROPERTY_CATALOG_READ_MODE")})'
```

The result must show PostgreSQL and ClickHouse present, Kafka and the unified
consumer absent, `producer_mode` equal to `disabled`, and `read_mode` equal to
`off`.

Build and test both Go processes:

```bash
cd fi-collector
go build ./cmd/fi-collector ./cmd/fi-property-catalog-consumer
go test ./...
docker build -t futureagi/fi-collector:property-catalog-oss-audit .
cd ..
```

Run the backend catalog contract, lifecycle, and definition/value API suite:

```bash
cd futureagi
uv sync --frozen --group dev
uv run pytest -q \
  tracer/services/clickhouse/v2/test_catalog_dev_schema.py \
  tracer/services/clickhouse/v2/test_property_catalog_schema_contract.py \
  tracer/tests/test_property_catalog_*.py \
  tracer/tests/test_unified_property_catalog_*.py \
  tracer/tests/test_attribute_catalog_dev_snapshot.py \
  tfc/temporal/schedules/tests/test_property_catalog.py
cd ..
```

The full live qualification starts only after following every preflight,
credential, isolated-schema, topic, bootstrap, status, and activation gate in
the canonical DEV Docker guide. A running broker by itself is not an
end-to-end property catalog.
