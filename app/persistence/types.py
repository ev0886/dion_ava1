from __future__ import annotations

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import MappedColumn, mapped_column

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
