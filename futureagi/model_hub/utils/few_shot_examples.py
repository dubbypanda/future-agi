from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID


def expand_static_few_shot_examples(
    few_shot_examples: list[dict] | None,
    organization=None,
) -> list[dict]:
    """
    Resolve eval config few-shot entries into the literal examples expected by
    CustomPromptEvaluator.
    """
    if not few_shot_examples:
        return []

    literal_examples: list[dict] = []
    dataset_ids: list[str] = []

    for example in few_shot_examples:
        if not isinstance(example, dict):
            continue

        if "input" in example or "output" in example:
            literal_examples.append(example)
            continue

        dataset_id = example.get("id")
        if _is_uuid(dataset_id):
            dataset_ids.append(str(dataset_id))

    if not dataset_ids:
        return literal_examples

    return literal_examples + _examples_from_datasets(dataset_ids, organization)


def _examples_from_datasets(
    dataset_ids: Iterable[str], organization=None
) -> list[dict]:
    from model_hub.models.develop_dataset import Cell, Column, Dataset, Row

    ordered_ids = list(dict.fromkeys(str(dataset_id) for dataset_id in dataset_ids))
    dataset_filter = {"id__in": ordered_ids, "deleted": False}
    if organization is not None:
        dataset_filter["organization"] = organization

    datasets = Dataset.objects.filter(**dataset_filter)
    datasets_by_id = {str(dataset.id): dataset for dataset in datasets}

    examples: list[dict] = []
    for dataset_id in ordered_ids:
        dataset = datasets_by_id.get(dataset_id)
        if dataset is None:
            continue

        columns = Column.objects.filter(dataset=dataset, deleted=False)
        columns_by_name = {}
        for column in columns:
            normalized_name = column.name.strip().lower()
            columns_by_name.setdefault(normalized_name, column)

        input_column = columns_by_name.get("input")
        output_column = columns_by_name.get("output")
        if input_column is None or output_column is None:
            continue

        score_column = columns_by_name.get("score")
        selected_columns = [input_column, output_column]
        if score_column is not None:
            selected_columns.append(score_column)

        rows = list(
            Row.objects.filter(dataset=dataset, deleted=False).order_by(
                "order", "created_at"
            )
        )
        if not rows:
            continue

        cells = Cell.objects.filter(
            dataset=dataset,
            row__in=rows,
            column__in=selected_columns,
            deleted=False,
        ).select_related("row", "column")

        values_by_row_id: dict[str, dict[str, str]] = {}
        for cell in cells:
            row_values = values_by_row_id.setdefault(str(cell.row_id), {})
            row_values[cell.column.name.strip().lower()] = (
                "" if cell.value is None else str(cell.value)
            )

        for row in rows:
            row_values = values_by_row_id.get(str(row.id), {})
            input_value = row_values.get("input", "")
            output_value = row_values.get("output", "")
            if not input_value or not output_value:
                continue

            example = {"input": input_value, "output": output_value}
            if "score" in row_values:
                example["score"] = row_values["score"]
            examples.append(example)

    return examples


def _is_uuid(value) -> bool:
    if value is None:
        return False
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
