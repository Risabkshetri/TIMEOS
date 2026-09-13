"""Declarative base for all ORM models.

The naming convention gives every constraint/index a deterministic name, so Alembic's
autogenerate produces stable, reviewable migrations instead of hash-suffixed names that differ
between environments.
"""

from datetime import datetime

from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # §9.3: "always TIMESTAMPTZ, never naive timestamp". Mapping this once here means every
    # `Mapped[datetime]` column, in every model, gets timezone=True without repeating the type
    # at each call site — the risk of one model quietly getting a naive column is structural,
    # not a per-file discipline problem.
    type_annotation_map = {
        datetime: TIMESTAMP(timezone=True),
    }
