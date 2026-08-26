# Unified property catalog: OSS/local compatibility

This page defines the authoritative non-EE setup for the unified property
catalog. The root OSS `docker-compose.yml` starts the unified Kafka pipeline by
default. No `ee.*` package is required.

## Keep the two catalog paths separate

| Path | Producer switch | Consumer | Purpose |
| --- | --- | --- | --- |
| Unified property catalog | `FI_PROPERTY_CATALOG_MODE` | `fi-property-catalog-consumer` | System, eval, annotation, dataset, simulation, and span-attribute properties |
| Legacy span attributes | `FI_CATALOG_MODE` | `fi-catalog-consumer` | Pre-release span-attribute-only catalog |

Never enable both switches in one collector. Root OSS keeps
`FI_CATALOG_MODE=disabled` and defaults `FI_PROPERTY_CATALOG_MODE=kafka`. The
topic initializer in `docker-compose.catalog-kafka.dev.yml` remains a separate,
profile-gated legacy harness; root OSS creates only
`futureagi.oss.property-catalog.v1` unless that unified topic is overridden.

## Authoritative local arrangement

There are two deliberate arrangements:

1. The root `docker-compose.yml` is the one-command OSS path. It starts an
   internal KRaft broker, creates the unified topic, creates one isolated
   `th7247_catalog_dev_*` database with the six pinned tables, provisions
   separate source/control/consumer/ledger/API identities, runs the unified
   consumer, enables the unified producer in development-only
   `revision_fence` scope, and starts the read-only workspace supervisor. The
   supervisor discovers local workspaces and projects from PostgreSQL, opens
   bounded revisions, and runs initial or incremental reconciliation. A tenant
   is admitted to the producer only while its exact current fence is present.
2. The checked-in
   [`deploy/dev/property-catalog-docker` bundle](../deploy/dev/property-catalog-docker/README.md).
   is the stricter operator-driven qualification path. Despite its directory
   name, its catalog implementation is OSS-owned: it
   runs the Go producer and consumer from `fi-collector/` and the Python
   catalog code under
   `futureagi/tracer/services/clickhouse/v2/property_catalog/`. It does not
   import `ee.*`.

The qualification renderer has an explicit OSS format,
`futureagi.property-catalog-oss-dev-docker`. It requires a reviewed operator
image built from `Dockerfile.oss`, keeps `CLOUD_DEPLOYMENT` unset through
bootstrap and steady state, and otherwise retains the same isolated database,
Kafka, credential, and activation gates. Use
`deploy/dev/property-catalog-docker/config.oss.example.yaml` as the fail-closed
starting point. This path expects a qualification stack originally initialized
with `CH25_DATABASE=futureagi`; it must not be used to rename or repoint an
existing self-host database.

The root stack preserves the same boundaries with local defaults. All secrets,
Kafka retention/partitions, polling intervals, lifecycle walls, epoch,
projection, producer stream, source database, and isolated target database are
environment-overridable. The target database must retain the
`th7247_catalog_dev_` prefix. The bootstrap scripts reject source/target
identity, unknown database names, malformed credentials, and any target that
does not contain exactly the six pinned tables.

User-facing catalog reads remain `off` by default. That is intentional: a new
install has no workspace until onboarding, and forcing `read` before its first
activation would turn an otherwise healthy OSS page into a 503. The Kafka
producer, consumer, schema, and reconciliation catalog are on; read cutover is
performed only after activation and an explicit workspace allowlist.

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
python3 -c 'import json; d=json.load(open("/tmp/futureagi-oss-compose.json")); s=d["services"]; print({"postgres": "postgres" in s, "clickhouse": "clickhouse" in s, "kafka": "property-catalog-kafka" in s, "unified_consumer": "fi-property-catalog-consumer" in s, "supervisor": "property-catalog-supervisor" in s, "producer_mode": s["fi-collector"]["environment"].get("FI_PROPERTY_CATALOG_MODE"), "scope_mode": s["fi-collector"]["environment"].get("FI_PROPERTY_CATALOG_WORKSPACE_SCOPE_MODE"), "read_mode": s["backend"]["environment"].get("PROPERTY_CATALOG_READ_MODE")})'
```

The result must show PostgreSQL, ClickHouse, Kafka, the unified consumer, and
the supervisor present; `producer_mode` must be `kafka`, `scope_mode` must be
`revision_fence`, and `read_mode` must remain `off` until explicit cutover.

Start only the catalog dependencies in a disposable Compose project when doing
a first-boot qualification. Never run `down -v` against an existing OSS
project:

```bash
docker compose -p futureagi-catalog-proof -f docker-compose.yml up -d \
  postgres clickhouse redis \
  property-catalog-postgres-bootstrap \
  property-catalog-clickhouse-bootstrap \
  property-catalog-kafka property-catalog-topic-init \
  fi-property-catalog-consumer fi-collector property-catalog-supervisor
docker compose -p futureagi-catalog-proof -f docker-compose.yml ps
```

The bootstrap jobs must exit `0`; Kafka, the consumer, collector, and
supervisor must remain running. Before any workspace exists the producer may
have no fence. Do not create an empty fence file: the supervisor publishes the
first canonical fence after onboarding creates a workspace and project.

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

The stricter live qualification still follows every preflight, credential,
isolated-schema, topic, bootstrap, status, and activation gate in the canonical
DEV Docker guide. A running broker by itself is not an end-to-end property
catalog.
