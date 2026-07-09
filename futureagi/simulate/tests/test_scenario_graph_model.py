"""Model-level regression guards for the ScenarioGraph workspace kwarg.

Two call sites in ``tfc/temporal/simulate/activities.py`` used to pass
``workspace=`` to ``ScenarioGraph.objects.create(...)``, which the model
does not declare. Django's strict constructor raised ``TypeError`` and
the activity marked the parent Scenario as FAILED. Every other call site
in the codebase already omits the kwarg; ``ScenarioGraph`` is a child of
``Scenario`` and workspace scoping flows transitively through the parent.

These tests pin the invariant so a future refactor cannot reintroduce it.
"""

from __future__ import annotations

import pytest

from simulate.models.scenario_graph import ScenarioGraph
from simulate.models.scenarios import Scenarios


@pytest.fixture
def scenario(db, organization, workspace):
    """Minimal Scenario the ScenarioGraph FK can point at.

    Skips agent_definition / simulator_agent / dataset because none of them
    are needed to exercise ``ScenarioGraph.objects.create``.
    """
    return Scenarios.objects.create(
        name="Workflow Builder Scenario",
        source="",
        scenario_type=Scenarios.ScenarioTypes.GRAPH,
        organization=organization,
        workspace=workspace,
    )


@pytest.mark.django_db
def test_scenario_graph_rejects_workspace_kwarg(organization, scenario):
    """The model does not declare a workspace field; passing one must
    raise so a future refactor cannot silently reintroduce the outage.
    """
    with pytest.raises(TypeError, match="workspace"):
        ScenarioGraph.objects.create(
            scenario=scenario,
            organization=organization,
            name="Reject me",
            workspace=scenario.workspace,
        )


@pytest.mark.django_db
def test_scenario_graph_create_without_workspace_succeeds(
    organization, scenario
):
    """Only the fields the model declares. This is exactly the call shape
    the two fixed sites in ``tfc/temporal/simulate/activities.py`` now use,
    and every other caller across ``simulate/`` and ``ee/agenthub/`` uses.
    """
    graph = ScenarioGraph.objects.create(
        scenario=scenario,
        organization=organization,
        name=f"{scenario.name} - Graph",
        description=f"Graph for {scenario.name}",
        graph_config={"graph_data": {"nodes": []}, "source": "user_provided"},
    )

    assert graph.id is not None
    assert graph.scenario_id == scenario.id
    assert graph.organization_id == organization.id
    assert graph.graph_config == {
        "graph_data": {"nodes": []},
        "source": "user_provided",
    }


@pytest.mark.django_db
def test_scenario_graph_model_does_not_declare_workspace_field():
    """Guards against a future migration that adds the field without
    also revisiting every caller. If someone genuinely needs to add
    workspace to ScenarioGraph, this test flips and forces a design
    conversation before merge.
    """
    field_names = {f.name for f in ScenarioGraph._meta.get_fields()}
    assert "workspace" not in field_names
