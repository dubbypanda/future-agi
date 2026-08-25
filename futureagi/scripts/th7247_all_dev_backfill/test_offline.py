#!/usr/bin/env python3
"""Offline safety contracts for the all-DEV property-catalog backfill."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PACKAGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))

import backfill_all_dev as backfill  # noqa: E402, I001


ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_A = "33333333-3333-4333-8333-333333333333"
PROJECT_B = "44444444-4444-4444-8444-444444444444"


class AllDevScopeTests(unittest.TestCase):
    def test_scope_inventory_is_limited_to_active_observe_projects(self) -> None:
        args = SimpleNamespace(
            postgres_container="postgres",
            postgres_user="reader",
            postgres_database="tfc",
            expected_workspaces=1,
            expected_projects=2,
        )
        completed = SimpleNamespace(
            stdout=(f"{ORGANIZATION_ID}\t{WORKSPACE_ID}\t{PROJECT_A},{PROJECT_B}\n")
        )

        with mock.patch.object(backfill, "_run", return_value=completed) as run:
            scopes = backfill._load_scopes(args)

        self.assertEqual(scopes[0].project_ids, (PROJECT_A, PROJECT_B))
        sql = run.call_args.args[0][-1]
        self.assertIn("p.trace_type = 'observe'", sql)
        self.assertIn("WHERE NOT p.deleted", sql)

    def test_legacy_inventory_counts_active_observe_projects(self) -> None:
        args = SimpleNamespace(
            postgres_container="postgres",
            postgres_user="reader",
            postgres_database="tfc",
        )
        with mock.patch.object(
            backfill,
            "_run",
            return_value=SimpleNamespace(stdout="2\n"),
        ) as run:
            count = backfill._legacy_null_workspace_count(args)

        self.assertEqual(count, 2)
        sql = run.call_args.args[0][-1]
        self.assertIn("trace_type='observe'", sql)
        self.assertIn("workspace_id IS NULL", sql)

    def test_active_scope_is_bound_to_immutable_build_plan_projects(self) -> None:
        plan = {
            "organization_id": ORGANIZATION_ID,
            "workspace_id": WORKSPACE_ID,
            "source_scope": {"project_ids": [PROJECT_A, PROJECT_B]},
        }
        row = f"{ORGANIZATION_ID}\t{WORKSPACE_ID}\t{json.dumps(plan)}\n"

        with mock.patch.object(backfill, "_clickhouse_query", return_value=row):
            scopes = backfill._active_scopes(SimpleNamespace())

        self.assertEqual(
            scopes[(ORGANIZATION_ID, WORKSPACE_ID)], (PROJECT_A, PROJECT_B)
        )

    def test_active_scope_rejects_plan_tenant_mismatch(self) -> None:
        plan = {
            "organization_id": "55555555-5555-4555-8555-555555555555",
            "workspace_id": WORKSPACE_ID,
            "source_scope": {"project_ids": [PROJECT_A]},
        }
        row = f"{ORGANIZATION_ID}\t{WORKSPACE_ID}\t{json.dumps(plan)}\n"

        with (
            mock.patch.object(backfill, "_clickhouse_query", return_value=row),
            self.assertRaisesRegex(backfill.BackfillError, "scope is inconsistent"),
        ):
            backfill._active_scopes(SimpleNamespace())


if __name__ == "__main__":
    unittest.main()
