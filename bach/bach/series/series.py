"""
Copyright 2021 Objectiv B.V.
"""
from abc import ABC, abstractmethod
from copy import copy
from typing import Optional, Dict, Tuple, Union, Type, Any, List, cast, TYPE_CHECKING, Callable, Mapping
from uuid import UUID

import pandas

from bach import DataFrame, SortColumn, DataFrameOrSeries, get_series_type_from_dtype

from bach.dataframe import ColumnFunction, dict_name_series_equals
from bach.expression import Expression, NonAtomicExpression, ConstValueExpression, \
    IndependentSubqueryExpression, SingleValueExpression, AggregateFunctionExpression
from sql_models.util import quote_identifier
from bach.types import value_to_dtype
from sql_models.model import SqlModel

if TYPE_CHECKING:
    from bach.partitioning import GroupBy, Window
    from bach.series import SeriesBoolean


WrappedPartition = Union['GroupBy', 'DataFrame']
WrappedWindow = Union['Window', 'DataFrame']


class Series(ABC):
    """
    A typed representation of a single column of data.

    It can be used as a separate object to just deal with a single list of values. There are many standard
    operations on Series available to do operations like add or subtract, to create aggregations like
    :py:meth:`~bach.dataframe.DataFrame.nunique()` or :py:meth:`~bach.dataframe.DataFrame.count()`,
    or to create new sub-Series, like :py:meth:`~bach.dataframe.DataFrame.unique()`.
    """
    # A series is defined by an expression and a name, and it exists within the scope of the base_node.
    # Its index can be a simple (dict of) Series in case of an already materialised base_node.
    # If group_by has been set, the index represents the future index of this Series. The series is now part
    # of the aggregation as defined by the GroupBy and base_node and
    # can only be evaluated as such.
    #
    # * Mostly immutable *
    # The attributes of this class are either immutable, or this class is guaranteed not
    # to modify them and the property accessors always return a copy. One exception tho: `engine` is mutable
    # and is shared with other Series and DataFrames that can change it's state.
    def __init__(self,
                 engine,
                 base_node: SqlModel,
                 index: Dict[str, 'Series'],
                 name: str,
                 expression: Expression,
                 group_by: Optional['GroupBy'],
                 sorted_ascending: Optional[bool] = None):
        """
        Initialize a new Series object.
        If a Series is associated with a DataFrame. The engine, base_node and index
        should match, as well as group_by (can be None, but then both are). Additionally the name
        should match the name of this Series object in the DataFrame.

        A Series can also become a future aggregation, and thus decoupled from its current
        DataFrame. In that case, the index will be set to the future index. If this Series is
        decoupled from its dataframe, by df['series'] for example, the series will have group_by
        set to the dataframe's groupby, to express that aggregation still has to take place.
        A series in that state can be combined back into a dataframe that has the same aggregation
        set-up (e.g. matching base_node, index and group_by)

        To create a new Series object from scratch there are class helper methods
        from_const(), get_class_instance().
        It is very common to clone a Series with little changes. Use copy_override() for that.

        :param engine: db connection
        :param base_node: sql-model of a select statement that must contain the columns/expressions that
            expression relies on.
        :param index: {} if this Series is part of an index, or a dict with the Series that are
            this Series' index. If this series is part of an aggregation that still needs to take place,
            the index will be a GroupBy instance expressing that future aggregation.
        :param name: name of this Series
        :param expression: Expression that this Series represents
        :param group_by: The requested aggregation for this series.
        :param sorted_ascending: None for no sorting, True for sorted ascending, False for sorted descending
        """
        self._engine = engine
        self._base_node = base_node
        self._index = copy(index)
        self._name = name
        self._expression = expression
        self._group_by = group_by
        self._sorted_ascending = sorted_ascending

    @property
    @classmethod
    @abstractmethod
    def dtype(cls) -> str:
        """
        The dtype of this Series.

        The dtype is used to uniquely identify data of the type that is
        represented by this Series subclass. The dtype should be unique among all Series
        subclasses.
        """
        raise NotImplementedError()

    @property
    @classmethod
    def dtype_aliases(cls) -> Tuple[Union[Type, str], ...]:
        """
        One or more aliases for the dtype.
        For example a BooleanSeries might have dtype 'bool', and as an alias the string 'boolean' and
        the builtin `bool`. An alias can be used in a similar way as the real dtype, e.g. to cast data to a
        certain type: `x.astype('boolean')` is the same as `x.astype('bool')`.

        Subclasses can override this value to indicate what strings they consider aliases for their dtype.
        """
        return tuple()

    @property
    def dtype_to_pandas(self) -> Optional[str]:
        """
        The dtype of this Series in a pandas.Series. Defaults to None
        Override to cast specifically, and set to None to let pandas choose.
        """
        return None

    @property
    @classmethod
    def supported_db_dtype(cls) -> Optional[str]:
        """
        Database level data type, that can be expressed using this Series type.
        Example: 'double precision' for a float in Postgres

        Subclasses should override this value if they intend to be the default class to handle such types.
        When creating a DataFrame from existing data in a database, this field will be used to
        determine what Series to instantiate for a column.
        """
        return None

    @property
    @classmethod
    def supported_value_types(cls) -> Tuple[Type, ...]:
        """
        List of python types that can be converted to database values using
        the `supported_value_to_expression()` method.

        Subclasses can override this value to indicate what types are supported
        by supported_value_to_expression().
        """
        return tuple()

    @classmethod
    @abstractmethod
    def supported_value_to_expression(cls, value: Any) -> Expression:
        """
        Give the expression for the given value. Consider calling the wrapper value_to_expression() instead.

        Implementations of this function are responsible for correctly quoting and escaping special
        characters in the given value. Either by using ExpressionTokens that allow unsafe values (e.g.
        StringValueToken), or by making sure that the quoting and escaping is done already on the value
        inside the ExpressionTokens.

        Implementations only need to be able to support the value specified by supported_value_types.

        :param value: All values of types listed by self.supported_value_types should be supported.
        :return: Expression representing the the value
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def dtype_to_expression(cls, source_dtype: str, expression: Expression) -> Expression:
        """
        Give the sql expression to convert the given expression, of the given source dtype to the dtype of
        this Series.
        :return: sql expression
        """
        raise NotImplementedError()

    @property
    def engine(self):
        """
        Get this Series' engine
        """
        return self._engine

    @property
    def base_node(self) -> SqlModel:
        """
        Get this Series' base_node
        """
        return self._base_node

    @property
    def index(self) -> Dict[str, 'Series']:
        """
        Get this Series' index dictionary {name: Series}
        """
        return copy(self._index)

    @property
    def name(self) -> str:
        """
        Get this Series' name
        """
        return self._name

    @property
    def group_by(self) -> Optional['GroupBy']:
        """
        Get this Series' group_by, if any.
        """
        return copy(self._group_by)

    @property
    def sorted_ascending(self) -> Optional[bool]:
        """
        Get this Series' sorting, if any
        """
        return self._sorted_ascending

    @property
    def expression(self) -> Expression:
        return self._expression

    @classmethod
    def get_class_instance(
            cls,
            base: DataFrameOrSeries,
            name: str,
            expression: Expression,
            group_by: Optional['GroupBy'],
            sorted_ascending: Optional[bool] = None
    ):
        """ Create an instance of this class. """
        return cls(
            engine=base.engine,
            base_node=base.base_node,
            index=base.index,
            name=name,
            expression=expression,
            group_by=group_by,
            sorted_ascending=sorted_ascending
        )

    @classmethod
    def value_to_expression(cls, value: Optional[Any]) -> Expression:
        """
        Give the expression for the given value.
        Wrapper around cls.supported_value_to_expression() that handles two generic cases:
            If value is None a simple 'NULL' expresison is returned.
            If value is not in supported_value_types raises an error.
        :raises TypeError: if value is not an instance of cls.supported_value_types, and not None
        """
        # We should wrap this in a ConstValueExpression or something
        if value is None:
            return Expression.raw('NULL')
        supported_types = cast(Tuple[Type, ...], cls.supported_value_types)  # help mypy
        if not isinstance(value, supported_types):
            raise TypeError(f'value should be one of {supported_types}'
                            f', actual type: {type(value)}')
        return cls.supported_value_to_expression(value)

    @classmethod
    def from_const(cls,
                   base: DataFrameOrSeries,
                   value: Any,
                   name: str) -> 'Series':
        """
        Create an instance of this class, that represents a column with the given value.
        The returned Series will be similar to the Series given as base. In case a DataFrame is given,
        it can be used immediately with that frame.
        :param base:    The DataFrame or Series that the internal parameters are taken from
        :param value:   The value that this constant Series will have
        :param name:    The name that it will be known by (only for representation)
        """
        result = cls.get_class_instance(
            base=base,
            name=name,
            expression=ConstValueExpression(cls.value_to_expression(value)),
            group_by=None,
        )
        return result

    def copy_override(self,
                      dtype=None,
                      engine=None,
                      base_node=None,
                      index=None,
                      name=None,
                      expression=None,
                      group_by: List[Union['GroupBy', None]] = None,  # List so [None] != None
                      sorted_ascending=None):
        """
        Big fat warning: group_by can legally be None, but if you want to set that,
        set the param in a list: [None], or [someitem]. If you set None, it will be left alone.
        """
        klass = self.__class__ if dtype is None else get_series_type_from_dtype(dtype)
        return klass(
            engine=self._engine if engine is None else engine,
            base_node=self._base_node if base_node is None else base_node,
            index=self._index if index is None else index,
            name=self._name if name is None else name,
            expression=self._expression if expression is None else expression,
            group_by=self._group_by if group_by is None else group_by[0],
            sorted_ascending=self._sorted_ascending if sorted_ascending is None else sorted_ascending
        )

    def get_column_expression(self, table_alias: str = None) -> Expression:
        expression = self.expression.resolve_column_references(table_alias)
        quoted_column_name = quote_identifier(self.name)
        if expression.to_sql() == quoted_column_name:
            return expression

        return Expression.construct('{} as {}', expression, Expression.raw(quoted_column_name))

    def _get_supported(self, operation_name: str, supported_dtypes: Tuple[str, ...], other: 'Series'):
        """
        Check whether `other` is supported for this operation, and if not, possibly do something
        about it by using subquery / materialization
        """
        if not (other.expression.is_constant or other.expression.is_independent_subquery):
            # we should maybe create a subquery
            if self.base_node != other.base_node or self.group_by != other.group_by:
                if other.expression.is_single_value:
                    other = self.as_independent_subquery(other)
                else:
                    # TODO improve error
                    raise ValueError("rhs has a different base_node or group_by, but contains more than one "
                                     "value. This is not supported.")

        if other.dtype.lower() not in supported_dtypes:
            raise TypeError(f'{operation_name} not supported between {self.dtype} and {other.dtype}.')
        return other

    def to_pandas(self, limit: Union[int, slice] = None) -> pandas.Series:
        """
        Get the data from this series as a pandas.Series
        :param limit: The limit to apply, either as a max amount of rows or a slice.
        """
        return self.to_frame().to_pandas(limit=limit)[self.name]

    def head(self, n: int = 5) -> pandas.Series:
        """
        Get the first n rows from this Series as a pandas.Series.
        :param n: The amount of rows to return.
        :note: This function queries the database.
        """
        return self.to_pandas(limit=n)

    @property
    def values(self):
        """
        .values property accessor akin pandas.Series.values
        :note: This function queries the database.
        """
        return self.to_pandas().values

    @property
    def value(self):
        """
        Retrieve the actual single value of this series. If it's not sure that there is only one value,
        a ValueError is raised. In that case use Series.values[0] to retrieve the value.

        :note: This function queries the database.
        """
        if not self.expression.is_single_value:
            raise ValueError('value accessor only supported for single value expressions. '
                             'Use .values instead')
        return self.values[0]

    @property
    def array(self):
        """
        .array property accessor akin pandas.Series.array
        :note: This function queries the database.
        """
        return self.to_pandas().array

    def sort_values(self, ascending=True):
        """
        Sort this Series by its values.
        Returns a new instance and does not actually modify the instance it is called on.
        :param ascending: Whether to sort ascending (True) or descending (False)
        """
        if self._sorted_ascending is not None and self._sorted_ascending == ascending:
            return self
        return self.copy_override(sorted_ascending=ascending)

    def view_sql(self):
        return self.to_frame().view_sql()

    def to_frame(self) -> DataFrame:
        """
        Create a DataFrame with the index and data from this Series.

        The DataFrame returned has the grouping and sorting also set like this Series had.
        """
        if self._sorted_ascending is not None:
            order_by = [SortColumn(expression=self.expression, asc=self._sorted_ascending)]
        else:
            order_by = []
        return DataFrame(
            engine=self._engine,
            base_node=self._base_node,
            index=self._index,
            series={self._name: self},
            group_by=self._group_by,
            order_by=order_by
        )

    @staticmethod
    def as_independent_subquery(series, operation: str = None, dtype: str = None) -> 'Series':
        """
        Get a series representing an independent subquery, created by materializing the series given
        and crafting a subquery expression from it, possibly adding the given operation.

        :note: This will maintain Expression.is_single_value status
        """
        # This will give us a dataframe that contains our series as a materialized column in the base_node
        df = series.to_frame().materialize()
        fmt_string = f'{operation} (SELECT {{}} FROM {{}})' if operation else f'(SELECT {{}} FROM {{}})'
        expr = IndependentSubqueryExpression.construct(fmt_string,
                                                       Expression.column_reference(series.name),
                                                       Expression.model_reference(df.base_node))

        if series.expression.is_single_value:
            # The expression is lost when materializing
            expr = SingleValueExpression(expr)

        s = series.copy_override(expression=expr, dtype=dtype, index={}, group_by=[None])
        return s

    def exists(self):
        """
        Boolean operation that returns True if there are one or more values in this Series
        """
        s = Series.as_independent_subquery(self, 'exists', dtype='bool')
        return s.copy_override(expression=SingleValueExpression(s.expression))

    def any_value(self):
        """
        For every row in this Series, do multiple evaluations where _any_ sub-evaluation should be True

        Example: a > b.any() evaluates to True is a > b for any value of b.
        """
        return Series.as_independent_subquery(self, 'any')

    def all_values(self):
        """
        For every row in this Series, do multiple evaluations where _all_ sub-evaluations should be True

        Example: a > b.all() evaluates to True is a > b for all values of b.
        """
        return Series.as_independent_subquery(self, 'all')

    def isin(self, other: 'Series'):
        """
        Evaluate for every row in this series whether the value is contained in other

        Example: a.isin(b) evaluates to True for a specific row if a > b for all values of b.
        """
        in_expr = Expression.construct('{} {}', self, Series.as_independent_subquery(other, 'in'))
        return self.copy_override(expression=in_expr, dtype='boolean')

    def astype(self, dtype: Union[str, Type]) -> 'Series':
        """
        Convert this Series to another type.

        A Series will be returned with the correct type set, if the conversion is available. An appropriate
        Exception will be raised if impossible to convert.
        """
        if dtype == self.dtype or dtype in self.dtype_aliases:
            return self
        series_type = get_series_type_from_dtype(dtype)
        expression = series_type.dtype_to_expression(self.dtype, self.expression)
        # get the real dtype, in case the provided dtype was an alias. mypy needs some help
        new_dtype = cast(str, series_type.dtype)
        return self.copy_override(dtype=new_dtype, expression=expression)

    def equals(self, other: Any, recursion: str = None) -> bool:
        """
        Checks whether other is the same as self. This implements the check that would normally be
        implemented in __eq__, but we already use that method for other purposes.
        This strictly checks that other is the same type as self. If other is a subclass this will return
        False.
        """
        if not isinstance(other, self.__class__) or not isinstance(self, other.__class__):
            return False
        return (
                dict_name_series_equals(self.index, other.index) and
                self.engine == other.engine and
                self.base_node == other.base_node and
                self.name == other.name and
                self.expression == other.expression and
                # avoid loops here.
                (recursion == 'GroupBy' or self.group_by == other.group_by) and
                self._sorted_ascending == other._sorted_ascending
        )

    def __getitem__(self, key: Union[Any, slice]):
        """
        Get a single value from the series. This is not returning the value,
        use the .value accessor for that instead.
        """
        if isinstance(key, slice):
            raise NotImplementedError("index slices currently not supported")

        if len(self.index) == 0:
            raise Exception('Not supported on Series without index. '
                            'Use .values[index] instead.')
        if len(self.index) > 1:
            raise NotImplementedError('Index only implemented for simple indexes. '
                                      'Use .values[index] instead')

        frame = self.to_frame()
        # Apply Boolean selection on index == key, help mypy a bit
        frame = cast(DataFrame, frame[list(frame.index.values())[0] == key])
        # limit to 1 row, will make all series SingleValueExpression, and get that series.
        return frame[:1][self.name]

    def isnull(self):
        """
        Evaluate for every row in this series whether the value is missing or NULL.

        :note:  Only NULL values in the Series in the underlying sql table will return True. np.nan is not
                checked for.

        See Also
        --------
        notnull
        """
        expression_str = f'{{}} is null'
        expression = NonAtomicExpression.construct(
            expression_str,
            self
        )
        return self.copy_override(dtype='bool', expression=expression)

    def notnull(self):
        """
        Evaluate for every row in this series whether the value is not missing or NULL.

        :note:  Only NULL values in the Series in the underlying sql table will return True. np.nan is not
                checked for.

        See Also
        --------
        isnull
        """
        expression_str = f'{{}} is not null'
        expression = NonAtomicExpression.construct(
            expression_str,
            self
        )
        return self.copy_override(dtype='bool', expression=expression)

    def fillna(self, other):
        """
        Fill any NULL value with the given constant or other compatible Series

        In case a Series is given, the value from the same row is used to fill.

        :param other: The value to replace the NULL values with. Should be a supported
            type by the series, or a TypeError is raised. Can also be another Series
        :note: Pandas replaces np.nan values, we can only replace NULL.
        :note: you can replace None with None, have fun, forever!
        """
        return self._binary_operation(
            other=other, operation='fillna', fmt_str='COALESCE({}, {})',
            other_dtypes=tuple([self.dtype]))

    def _binary_operation(self, other: 'Series', operation: str, fmt_str: str,
                          other_dtypes: Tuple[str, ...] = (),
                          dtype: Union[str, Mapping[str, Optional[str]]] = None) -> 'Series':
        """
        The standard way to perform a binary operation

        :param self: The left hand side expression (lhs) in the operation
        :param other: The right hand side expression (rhs) in the operation
        :param operation: A user-readable representation of the operation
        :param fmt_str: An Expression.construct format string, accepting lhs and rhs as the only parameters,
            in that order.
        :param other_dtypes: The acceptable dtypes for the rhs expression
        :param dtype: The new dtype for the Series that results from this operation. Leave None for same
            as lhs, pass a string with the new explicit dtype, or pass a dict that maps rhs.dtype to the
            resulting dtype. If the dict does not contain the rhs.dtype, None is assumed, using the lhs
            dtype.
        """
        if len(other_dtypes) == 0:
            raise NotImplementedError(f'binary operation {operation} not supported '
                                      f'for {self.__class__} and {other.__class__}')

        other = const_to_series(base=self, value=other)
        other = self._get_supported(operation, other_dtypes, other)
        expression = NonAtomicExpression.construct(fmt_str, self, other)
        if isinstance(dtype, dict):
            if other.dtype not in dtype:
                dtype = None
            else:
                dtype = dtype[other.dtype]
        return self.copy_override(dtype=dtype, expression=expression)

    def _arithmetic_operation(self, other: 'Series', operation: str, fmt_str: str,
                              other_dtypes: Tuple[str, ...] = (),
                              dtype: Union[str, Mapping[str, Optional[str]]] = None) -> 'Series':
        """
        implement this in a subclass to have boilerplate support for all arithmetic functions
        defined below, but also call this method from specific arithmetic operation implementations
        without implementing it to get nice error messages in yield.

        :see: _binary_operation() for parameters
        """
        if len(other_dtypes) == 0:
            raise TypeError(f'arithmetic operation {operation} not supported for '
                            f'{self.__class__} and {other.__class__}')
        return self._binary_operation(other, operation, fmt_str, other_dtypes, dtype)

    def __add__(self, other) -> 'Series':
        return self._arithmetic_operation(other, 'add', '{} + {}')

    def __sub__(self, other) -> 'Series':
        return self._arithmetic_operation(other, 'sub', '{} - {}')

    def __truediv__(self, other) -> 'Series':
        """ This case is not generically okay. subclasses should check that"""
        return self._arithmetic_operation(other, 'div', '{} / {}')

    def __floordiv__(self, other) -> 'Series':
        return self._arithmetic_operation(other, 'floordiv', 'floor({} / {})', dtype='int64')

    def __mul__(self, other) -> 'Series':
        return self._arithmetic_operation(other, 'mul', '{} * {}')

    def __mod__(self, other) -> 'Series':
        # PG is picky in data types, so we solve it like this.
        # dividend - floor(dividend / divisor) * divisor';
        return self - self // other * other

    def __pow__(self, other, modulo=None) -> 'Series':
        if modulo is not None:
            return (self.__pow__(other, None)).__mod__(modulo)
        return self._arithmetic_operation(other, 'pow', 'POWER({}, {})')

    def __lshift__(self, other) -> 'Series':
        raise NotImplementedError()

    def __rshift__(self, other) -> 'Series':
        raise NotImplementedError()

    # Boolean operations
    def __invert__(self) -> 'Series':
        raise NotImplementedError()

    def __and__(self, other) -> 'Series':
        raise NotImplementedError()

    def __xor__(self, other) -> 'Series':
        raise NotImplementedError()

    def __or__(self, other) -> 'Series':
        raise NotImplementedError()

    # Comparator operations
    def _comparator_operation(self, other: 'Series', comparator: str,
                              other_dtypes: Tuple[str, ...] = ()) -> 'SeriesBoolean':
        if len(other_dtypes) == 0:
            raise TypeError(f'comparator {comparator} not supported for '
                            f'{self.__class__} and {other.__class__}')
        return cast('SeriesBoolean', self._binary_operation(
            other=other, operation=f"comparator '{comparator}'",
            fmt_str=f'{{}} {comparator} {{}}',
            other_dtypes=other_dtypes, dtype='bool'
        ))

    def __ne__(self, other) -> 'SeriesBoolean':     # type: ignore
        return self._comparator_operation(other, "<>")

    def __eq__(self, other) -> 'SeriesBoolean':     # type: ignore
        return self._comparator_operation(other, "=")

    def __lt__(self, other) -> 'SeriesBoolean':
        return self._comparator_operation(other, "<")

    def __le__(self, other) -> 'SeriesBoolean':
        return self._comparator_operation(other, "<=")

    def __ge__(self, other) -> 'SeriesBoolean':
        return self._comparator_operation(other, ">=")

    def __gt__(self, other) -> 'SeriesBoolean':
        return self._comparator_operation(other, ">")

    def apply_func(self, func: ColumnFunction, *args, **kwargs) -> List['Series']:
        """
        Apply the given functions to this Series.
        If multiple are given, a list of multiple new series will be returned.

        :param func: the function to look for on all series, either as a str, or callable,
                    or a list of such
        :param args: Positional arguments to pass through to the aggregation function
        :param kwargs: Keyword arguments to pass through to the aggregation function

        :note: you should probably not use this method directly.
        """
        if isinstance(func, str) or callable(func):
            func = [func]
        if not isinstance(func, list):
            raise TypeError(f'Unsupported type for func: {type(func)}')
        if len(func) == 0:
            raise Exception('Nothing to do.')

        series = {}
        for fn in func:
            if isinstance(fn, str):
                series_name = f'{self.name}_{fn}'
                fn = cast(Callable, getattr(self, fn))
            elif callable(fn):
                series_name = f'{self._name}_{fn.__name__}'
            else:
                raise ValueError("func {fn} is not callable")

            # If the method is bound yet (__self__ set), we need to use the unbound function
            # to make sure call the method on the right series
            if hasattr(fn, '__self__'):
                fn = cast(Callable, fn.__func__)  # type: ignore[attr-defined]

            fn_applied_series = fn(self, *args, **kwargs)
            if series_name in series:
                raise ValueError(f'duplicate series target name {series_name}')
            series[series_name] = fn_applied_series.copy_override(name=series_name)

        return list(series.values())

    def aggregate(self,
                  func: ColumnFunction,
                  group_by: 'GroupBy' = None,
                  *args, **kwargs) -> DataFrameOrSeries:
        """
        Alias for :py:meth:`agg()`.
        """
        return self.agg(func, group_by, *args, **kwargs)

    def agg(self,
            func: ColumnFunction,
            group_by: 'GroupBy' = None,
            *args, **kwargs) -> DataFrameOrSeries:
        """
        Apply one or more aggregation functions to this Series.

        :param func: the aggregation function to look for on all series.
            See GroupBy.agg() for supported arguments
        :param group_by: the group_by to use, or aggregation over full base_node if None
        :param args: Positional arguments to pass through to the aggregation function
        :param kwargs: Keyword arguments to pass through to the aggregation function
        :return: Aggregated Series, or DataFrame if multiple series are returned
        """
        if group_by is None:
            from bach.partitioning import GroupBy
            group_by = GroupBy([])

        series = self.apply_func(func, group_by, *args, **kwargs)
        if len(series) == 1:
            return series[0]

        return DataFrame(engine=self.engine,
                         base_node=self.base_node,
                         index=group_by.index,
                         series={s.name: s for s in series},
                         group_by=group_by,
                         order_by=[])

    def _check_unwrap_groupby(self,
                              wrapped: Union['DataFrame', 'GroupBy'],
                              isin=None, notin=()) -> 'GroupBy':
        """
        Unwrap the GroupBy from the Aggregator if one is given, else use the GroupBy directly
        and perform some checks:
        - Make sure that the GroupBy instance is of a type in the set `isin`, defaulting
          to make sure it's a GroupBy if `isin` is None
        - Make sure that it's instance type is not in `notin`

        Exceptions will be raised when check don't pass
        :returns: The potentially unwrapped GroupBy
        """
        from bach.partitioning import GroupBy
        isin = GroupBy if isin is None else isin

        if wrapped is not None and isinstance(wrapped, DataFrame):
            group_by = wrapped.group_by
        else:
            group_by = wrapped

        if not isinstance(group_by, isin):
            raise ValueError(f'group_by {type(group_by)} not in {isin}')
        if isinstance(group_by, notin):
            raise ValueError(f'group_by {type(group_by)} not supported')
        return group_by

    def _derived_agg_func(self,
                          partition: Optional[WrappedPartition],
                          expression: Union[str, Expression],
                          dtype: str = None,
                          skipna: bool = True,
                          min_count: int = None) -> 'Series':
        """
        Create a derived Series that aggregates underlying Series through the given expression.
        If no partition to aggregate on is given, and the Series does not have one set,
        it will create one that aggregates the entire series without any partitions.
        This allows for calls like:
          someseries.sum()

        Skipna will also be checked here as to make the callers life as simple as possible.
        :param partition: The Aggregator containing the GroupBy, or just the GroupBy
            to execute the expression within.
        :param expression: str or Expression of the aggregation function.
        :param dtype: Will be used for derived series if not None.
        :param skipna: skipna parameter for support check.
        :returns: The correctly typed derived Series, with either the current index in case of
            a Window function, or the GroupBy otherwise.
        """
        from bach.partitioning import GroupBy, Window

        if not skipna:
            raise NotImplementedError('Not skipping n/a is not supported')

        if self.expression.has_windowed_aggregate_function:
            raise ValueError(f'Cannot call an aggregation function on already windowed column '
                             f'`{self.name}` Try calling materialize() on the DataFrame'
                             f' this Series belongs to first.')

        if self.expression.has_aggregate_function:
            raise ValueError(f'Cannot call an aggregation function on already aggregated column '
                             f'`{self.name}` Try calling materialize() on the DataFrame'
                             f' this Series belongs to first.')

        if isinstance(expression, str):
            expression = AggregateFunctionExpression.construct(f'{expression}({{}})', self)

        if partition is None:
            if self._group_by:
                partition = self._group_by
            else:
                # create an aggregation over the entire input
                partition = GroupBy([])
        else:
            partition = self._check_unwrap_groupby(partition)

        if min_count is not None and min_count > 0:
            if isinstance(partition, Window):
                if partition.min_values != min_count:
                    raise NotImplementedError(
                        f'min_count conflicting with min_values in Window'
                        f'{min_count} != {partition.min_values}'
                    )
            else:
                expression = Expression.construct(
                    f'CASE WHEN {{}} >= {min_count} THEN {{}} ELSE NULL END',
                    self.count(partition, skipna=skipna), expression
                )

        derived_dtype = self.dtype if dtype is None else dtype

        if not isinstance(partition, Window):
            if self._group_by and self._group_by != partition:
                raise ValueError('passed partition does not match series partition. I\'m confused')

            # if the passed expression was not a str, make sure it's tagged correctly
            # we can't check the outer expression, because min_values logic above could have already wrapped
            # it.
            if not expression.has_aggregate_function:
                raise ValueError('Passed expression should contain an aggregation function')

            if partition.index == {}:
                # we're creating an aggregation on everything, this will yield one value
                expression = SingleValueExpression(expression)

            return self.copy_override(dtype=derived_dtype,
                                      index=partition.index,
                                      group_by=[partition],
                                      expression=expression)
        else:
            return self.copy_override(dtype=derived_dtype,
                                      expression=partition.get_window_expression(expression))

    def count(self, partition: WrappedPartition = None, skipna: bool = True):
        # count is not constant because it depends on the number of rows in the selection.
        # See the comment in Expression.AggregationFunctionExpression
        return self._derived_agg_func(partition, 'count', 'int64', skipna=skipna)

    def max(self, partition: WrappedPartition = None, skipna: bool = True):
        return self._derived_agg_func(partition, 'max', skipna=skipna)

    def median(self, partition: WrappedPartition = None, skipna: bool = True):
        return self._derived_agg_func(
            partition=partition,
            expression=AggregateFunctionExpression.construct(
                f'percentile_disc(0.5) WITHIN GROUP (ORDER BY {{}})', self),
            skipna=skipna
        )

    def min(self, partition: WrappedPartition = None, skipna: bool = True):
        return self._derived_agg_func(partition, 'min', skipna=skipna)

    def mode(self, partition: WrappedPartition = None, skipna: bool = True):
        return self._derived_agg_func(
            partition=partition,
            expression=AggregateFunctionExpression.construct(f'mode() within group (order by {{}})', self),
            skipna=skipna
        )

    def nunique(self, partition: WrappedPartition = None, skipna: bool = True):
        from bach.partitioning import Window
        if partition is not None:
            partition = self._check_unwrap_groupby(partition, notin=Window)
        return self._derived_agg_func(
            partition=partition, dtype='int64',
            expression=AggregateFunctionExpression.construct('count(distinct {})', self),
            skipna=skipna)

    # Window functions applicable for all types of data, but only with a window
    # TODO more specific docs
    # TODO make group_by optional, but for that we need to use current series sorting
    def _check_window(self, window: WrappedWindow) -> 'Window':
        """
        Validate that the given partition is a true Window or raise an exception
        """
        from bach.partitioning import Window
        return cast(Window, self._check_unwrap_groupby(window, isin=Window))

    def window_row_number(self, window: WrappedWindow):
        """
        Returns the number of the current row within its window, counting from 1.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('row_number()'), 'int64')

    def window_rank(self, window: WrappedWindow):
        """
        Returns the rank of the current row, with gaps; that is, the row_number of the first row
        in its peer group.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('rank()'), 'int64')

    def window_dense_rank(self, window: WrappedWindow):
        """
        Returns the rank of the current row, without gaps; this function effectively counts peer
        groups.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('dense_rank()'), 'int64')

    def window_percent_rank(self, window: WrappedWindow):
        """
        Returns the relative rank of the current row, that is
        (rank - 1) / (total partition rows - 1).
        The value thus ranges from 0 to 1 inclusive.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('percent_rank()'), "double precision")

    def window_cume_dist(self, window: WrappedWindow):
        """
        Returns the cumulative distribution, that is
        (number of partition rows preceding or peers with current row) / (total partition rows).
        The value thus ranges from 1/N to 1.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('cume_dist()'), "double precision")

    def window_ntile(self, window: WrappedWindow, num_buckets: int = 1):
        """
        Returns an integer ranging from 1 to the argument value,
        dividing the partition as equally as possible.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct(f'ntile({num_buckets})'), "int64")

    def window_lag(self, window: WrappedWindow, offset: int = 1, default: Any = None):
        """
        Returns value evaluated at the row that is offset rows before the current row within the window

        If there is no such row, instead returns default (which must be of the same type as value).
        Both offset and default are evaluated with respect to the current row.
        :param offset: The amount of rows to look back, default 1
        :param default: The value to return if no value is available, can be a constant value or Series.
        Defaults to None
        """
        window = self._check_window(window)
        default_expr = self.value_to_expression(default)
        return self._derived_agg_func(
            window,
            Expression.construct(f'lag({{}}, {offset}, {{}})', self, default_expr),
            self.dtype
        )

    def window_lead(self, window: WrappedWindow, offset: int = 1, default: Any = None):
        """
        Returns value evaluated at the row that is offset rows after the current row within the window.

        If there is no such row, instead returns default (which must be of the same type as value).
        Both offset and default are evaluated with respect to the current row.
        :param offset: The amount of rows to look forward, default 1
        :param default: The value to return if no value is available, can be a constant value or Series.
        Defaults to None
        """
        window = self._check_window(window)
        default_expr = self.value_to_expression(default)
        return self._derived_agg_func(
            window,
            Expression.construct(f'lead({{}}, {offset}, {{}})', self, default_expr),
            self.dtype
        )

    def window_first_value(self, window: WrappedWindow):
        """
        Returns value evaluated at the row that is the first row of the window frame.
        """
        window = self._check_window(window)
        return self._derived_agg_func(
            window,
            Expression.construct('first_value({})', self),
            self.dtype
        )

    def window_last_value(self, window: WrappedWindow):
        """
        Returns value evaluated at the row that is the last row of the window frame.
        """
        window = self._check_window(window)
        return self._derived_agg_func(window, Expression.construct('last_value({})', self), self.dtype)

    def window_nth_value(self, window: WrappedWindow, n: int):
        """
        Returns value evaluated at the row that is the n'th row of the window frame.
        (counting from 1); returns NULL if there is no such row.
        """
        window = self._check_window(window)
        return self._derived_agg_func(
            window,
            Expression.construct(f'nth_value({{}}, {n})', self),
            self.dtype
        )


# TODO remove from docs.
def const_to_series(base: Union[Series, DataFrame],
                    value: Union[Series, int, float, str, UUID],
                    name: str = None) -> Series:
    """
    Take a value and return a Series representing a column with that value.
    If value is already a Series it is returned unchanged unless it has no base_node set, in case
    it's a subquery. We create a copy and hook it to our base node in that case, so we can work with it.
    If value is a constant then the right BuhTuh subclass is found for that type and instantiated
    with the constant value.
    :param base: Base series or DataFrame. In case a new Series object is created and returned, it will
        share its engine, index, and base_node with this one. Only applies if value is not a Series
    :param value: constant value for which to create a Series, or a Series
    :param name: optional name for the series object. Only applies if value is not a Series
    :return:
    """
    if isinstance(value, Series):
        return value
    name = '__const__' if name is None else name
    dtype = value_to_dtype(value)
    series_type = get_series_type_from_dtype(dtype)
    return series_type.from_const(base=base, value=value, name=name)
