from __future__ import annotations

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SqlEnum, String
from sqlalchemy.orm import MappedColumn, mapped_column
from sqlalchemy.types import TypeDecorator

EnumType = TypeVar("EnumType", bound=Enum)


def enum_column(
    enum_type: type[EnumType],
    *,
    nullable: bool = False,
    index: bool = False,
    unique: bool = False,
) -> MappedColumn[EnumType]:
    return mapped_column(
        SqlEnum(
            enum_type,
            native_enum=False,
            validate_strings=True,
            length=max(len(member.value) for member in enum_type),
        ),
        nullable=nullable,
        index=index,
        unique=unique,
    )


class EnumValueType(TypeDecorator[EnumType]):
    impl = String
    cache_ok = True

    def __init__(self, enum_type: type[EnumType]) -> None:
        self.enum_type = enum_type
        super().__init__(length=max(len(member.value) for member in enum_type))

    def process_bind_param(self, value: EnumType | str | None, dialect) -> str | None:
        if value is None:
            return None
        return self._coerce(value).value

    def process_result_value(self, value: str | None, dialect) -> EnumType | None:
        if value is None:
            return None
        return self._coerce(value)

    def _coerce(self, value: EnumType | str) -> EnumType:
        if isinstance(value, self.enum_type):
            return value
        if isinstance(value, str):
            try:
                return self.enum_type(value)
            except ValueError:
                try:
                    return self.enum_type[value]
                except KeyError:
                    return self.enum_type[value.upper()]
        raise TypeError(f"Unsupported {self.enum_type.__name__} value: {value!r}")
