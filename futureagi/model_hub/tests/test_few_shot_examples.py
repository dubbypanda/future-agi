import pytest

from evaluations.engine.instance import prepare_eval_config
from model_hub.models.choices import DataTypeChoices, OwnerChoices, SourceChoices
from model_hub.models.develop_dataset import Cell, Column, Dataset, Row
from model_hub.models.evals_metric import EvalTemplate
from model_hub.utils.few_shot_examples import expand_static_few_shot_examples


def _create_dataset_with_rows(organization):
    dataset = Dataset.objects.create(
        name="few-shot-source",
        organization=organization,
    )
    input_column = Column.objects.create(
        name="input",
        data_type=DataTypeChoices.TEXT.value,
        dataset=dataset,
        source=SourceChoices.OTHERS.value,
    )
    output_column = Column.objects.create(
        name="output",
        data_type=DataTypeChoices.TEXT.value,
        dataset=dataset,
        source=SourceChoices.OTHERS.value,
    )
    score_column = Column.objects.create(
        name="score",
        data_type=DataTypeChoices.TEXT.value,
        dataset=dataset,
        source=SourceChoices.OTHERS.value,
    )

    rows = [Row.objects.create(dataset=dataset, order=i) for i in range(2)]
    values = [
        ("input 1", "output 1", "Passed"),
        ("input 2", "output 2", "Failed"),
    ]
    for row, (input_value, output_value, score_value) in zip(rows, values, strict=True):
        Cell.objects.create(
            dataset=dataset,
            row=row,
            column=input_column,
            value=input_value,
        )
        Cell.objects.create(
            dataset=dataset,
            row=row,
            column=output_column,
            value=output_value,
        )
        Cell.objects.create(
            dataset=dataset,
            row=row,
            column=score_column,
            value=score_value,
        )

    return dataset


@pytest.mark.django_db
def test_expand_static_few_shot_examples_resolves_dataset_refs(
    organization,
):
    dataset = _create_dataset_with_rows(organization)

    examples = expand_static_few_shot_examples(
        [{"id": str(dataset.id), "name": dataset.name}],
        organization=organization,
    )

    assert examples == [
        {"input": "input 1", "output": "output 1", "score": "Passed"},
        {"input": "input 2", "output": "output 2", "score": "Failed"},
    ]


@pytest.mark.django_db
def test_expand_static_few_shot_examples_preserves_literal_examples(
    organization,
):
    dataset = _create_dataset_with_rows(organization)
    literal = {"input": "literal input", "output": "literal output"}

    examples = expand_static_few_shot_examples(
        [literal, {"id": str(dataset.id), "name": dataset.name}],
        organization=organization,
    )

    assert examples[0] == literal
    assert examples[1:] == [
        {"input": "input 1", "output": "output 1", "score": "Passed"},
        {"input": "input 2", "output": "output 2", "score": "Failed"},
    ]


@pytest.mark.django_db
def test_prepare_eval_config_expands_few_shot_dataset_refs(organization):
    dataset = _create_dataset_with_rows(organization)
    template = EvalTemplate.no_workspace_objects.create(
        name="few-shot-eval",
        organization=organization,
        owner=OwnerChoices.USER.value,
        eval_type="llm",
        criteria="Check {{output}}",
        model="turing_small",
        config={
            "eval_type_id": "CustomPromptEvaluator",
            "output": "Pass/Fail",
            "rule_prompt": "Check {{output}}",
            "few_shot_examples": [{"id": str(dataset.id), "name": dataset.name}],
        },
    )

    config, _ = prepare_eval_config(
        eval_template=template,
        config={},
        model="turing_small",
        organization_id=str(organization.id),
    )

    assert config["few_shot_examples"] == [
        {"input": "input 1", "output": "output 1", "score": "Passed"},
        {"input": "input 2", "output": "output 2", "score": "Failed"},
    ]
