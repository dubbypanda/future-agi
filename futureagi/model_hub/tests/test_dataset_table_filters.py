import pytest

from model_hub.models.choices import DataTypeChoices, SourceChoices
from model_hub.models.develop_dataset import Cell, Column, Dataset, Row
from model_hub.views.develop_dataset import GetDatasetTableView


def _filter(column_id, filter_type, filter_op, filter_value=None):
    config = {
        "filter_type": filter_type,
        "filter_op": filter_op,
    }
    if filter_value is not None:
        config["filter_value"] = filter_value
    return {"column_id": str(column_id), "filter_config": config}


@pytest.fixture
def dataset_filter_seed(organization, workspace):
    dataset = Dataset.objects.create(
        name="Filter dataset",
        organization=organization,
        workspace=workspace,
    )
    text_col = Column.objects.create(
        name="status",
        data_type=DataTypeChoices.TEXT.value,
        dataset=dataset,
        source=SourceChoices.OTHERS.value,
    )
    bool_col = Column.objects.create(
        name="passed",
        data_type=DataTypeChoices.BOOLEAN.value,
        dataset=dataset,
        source=SourceChoices.OTHERS.value,
    )
    rows = [
        Row.objects.create(dataset=dataset, order=1),
        Row.objects.create(dataset=dataset, order=2),
        Row.objects.create(dataset=dataset, order=3),
    ]
    Cell.objects.create(dataset=dataset, row=rows[0], column=text_col, value="Alpha")
    Cell.objects.create(dataset=dataset, row=rows[1], column=text_col, value="Beta")
    Cell.objects.create(dataset=dataset, row=rows[2], column=text_col, value="")
    Cell.objects.create(dataset=dataset, row=rows[0], column=bool_col, value="true")
    Cell.objects.create(dataset=dataset, row=rows[1], column=bool_col, value="false")
    Cell.objects.create(dataset=dataset, row=rows[2], column=bool_col, value="")
    return dataset, rows, text_col, bool_col


def _apply(dataset, filters, columns):
    return list(
        GetDatasetTableView()
        ._apply_filters(
            Cell.objects.filter(dataset=dataset),
            Row.objects.filter(dataset=dataset),
            filters,
            [],
            {str(column.id): column for column in columns},
        )
        .order_by("order")
    )


def test_dataset_table_text_in_and_not_in_filters(dataset_filter_seed):
    dataset, rows, text_col, bool_col = dataset_filter_seed

    assert (
        _apply(
            dataset,
            [_filter(text_col.id, "text", "in", ["alpha", "beta"])],
            [text_col, bool_col],
        )
        == rows[:2]
    )
    assert (
        _apply(
            dataset,
            [_filter(text_col.id, "text", "not_in", ["alpha"])],
            [text_col, bool_col],
        )
        == rows[1:]
    )


def test_dataset_table_boolean_not_equals_and_null_filters(dataset_filter_seed):
    dataset, rows, text_col, bool_col = dataset_filter_seed

    assert (
        _apply(
            dataset,
            [_filter(bool_col.id, "boolean", "not_equals", "true")],
            [text_col, bool_col],
        )
        == rows[1:]
    )
    assert _apply(
        dataset,
        [_filter(text_col.id, "text", "is_null")],
        [text_col, bool_col],
    ) == [rows[2]]
    assert (
        _apply(
            dataset,
            [_filter(text_col.id, "text", "is_not_null")],
            [text_col, bool_col],
        )
        == rows[:2]
    )
