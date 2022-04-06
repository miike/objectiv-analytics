"""
Copyright 2021 Objectiv B.V.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Union, cast, Optional, NamedTuple
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.engine import Dialect, Engine

from bach import get_series_type_from_dtype, DataFrame
from bach.expression import Expression
from bach.savepoints import Savepoints
from bach.sql_model import BachSqlModel
from sql_models.model import CustomSqlModelBuilder


@dataclass(frozen=True)
class FakeEngine:
    """ Helper class that serves as a mock for SqlAlchemy Engine objects """
    dialect: Dialect
    name: str = field(init=False)
    url: str = 'postgresql://user@host:5432/db'

    def __post_init__(self):
        super().__setattr__('name', self.dialect.name)  # set the 'frozen' attribute self.name


def get_fake_df(
    index_names: List[str],
    data_names: List[str],
    dtype: Union[str, Dict[str, str]] = 'int64',
    dialect: Dialect = PGDialect()
) -> DataFrame:
    engine = FakeEngine(dialect=dialect)
    columns = index_names + data_names
    base_node = BachSqlModel.from_sql_model(
        sql_model=CustomSqlModelBuilder('select * from x', name='base')(),
        column_expressions={c: Expression.column_reference(c) for c in columns},
    )
    if isinstance(dtype, str):
        dtype = {
            col_name: dtype
            for col_name in index_names + data_names
        }

    index: Dict[str, 'Series'] = {}
    for name in index_names:
        series_type = get_series_type_from_dtype(dtype=dtype.get(name, 'int64'))
        index[name] = series_type(
            engine=engine,
            base_node=base_node,
            index={},
            name=name,
            expression=Expression.column_reference(name),
            group_by=cast('GroupBy', None),
            sorted_ascending=None,
            index_sorting=[]
        )

    data: Dict[str, 'Series'] = {}
    for name in data_names:
        series_type = get_series_type_from_dtype(dtype=dtype.get(name, 'int64'))
        data[name] = series_type(
            engine=engine,
            base_node=base_node,
            index=index,
            name=name,
            expression=Expression.column_reference(name),
            group_by=cast('GroupBy', None),
            sorted_ascending=None,
            index_sorting=[]
        )

    return DataFrame(engine=engine, base_node=base_node,
                     index=index, series=data, group_by=None, order_by=[], savepoints=Savepoints())


def get_fake_df_test_data(dialect: Dialect) -> DataFrame:
    return get_fake_df(
        index_names=['_index_skating_order'],
        data_names=['skating_order', 'city', 'municipality', 'inhabitants', 'founding'],
        dtype={
            '_index_skating_order': 'int64',
            'skating_order': 'int64',
            'city': 'string',
            'municipality': 'string',
            'inhabitants': 'int64',
            'founding': 'int64'
        },
        dialect=dialect
    )
