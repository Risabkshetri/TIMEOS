"""Seeds the default activity_categories taxonomy for a user (§15.3).

Idempotent and safe to call on every startup for every existing user, like
`timeos.jobs.partitions.ensure_partitions` — relies on the `uq_activity_categories_user_id_key`
unique constraint plus `ON CONFLICT DO NOTHING`, so re-running never duplicates or resets a
category the user has since renamed (a rename only touches `label`, never `key`).

`System` and its four children (Idle, Unobserved, Offline, Unknown) are `is_system=True` per
§15.3 ("System categories are immutable") — the pipeline assumes these four keys always exist for
every user, since they're the categories `coverage`-derived time (not real activity) maps to.
Everything else seeded here is a starting point the user is free to rename, merge, or extend.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.models.activity_category import ActivityCategory

# (key, label, is_system) for each top-level group, and its children.
TAXONOMY: list[tuple[str, str, bool, list[tuple[str, str, bool]]]] = [
    (
        "work",
        "Work",
        False,
        [
            ("deep_work", "Deep Work", False),
            ("focused_work", "Focused Work", False),
            ("development", "Development", False),
            ("research", "Research", False),
            ("writing", "Writing", False),
            ("meetings", "Meetings", False),
            ("admin", "Admin", False),
        ],
    ),
    (
        "growth",
        "Growth",
        False,
        [
            ("learning", "Learning", False),
            ("reading", "Reading", False),
            ("practice", "Practice", False),
        ],
    ),
    (
        "connection",
        "Connection",
        False,
        [
            ("communication", "Communication", False),
            ("social", "Social", False),
        ],
    ),
    (
        "life",
        "Life",
        False,
        [
            ("personal", "Personal", False),
            ("exercise", "Exercise", False),
            ("health", "Health", False),
            ("errands", "Errands", False),
        ],
    ),
    (
        "consumption",
        "Consumption",
        False,
        [
            ("entertainment", "Entertainment", False),
            ("browsing", "Browsing", False),
        ],
    ),
    (
        "system",
        "System",
        True,
        [
            ("idle", "Idle", True),
            ("unobserved", "Unobserved", True),
            ("offline", "Offline", True),
            ("unknown", "Unknown", True),
        ],
    ),
]

# The four leaf keys the pipeline hard-depends on existing for every user.
SYSTEM_LEAF_KEYS = frozenset({"idle", "unobserved", "offline", "unknown"})


async def ensure_system_categories(session: AsyncSession, user_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Ensures the full default taxonomy exists for `user_id`. Returns a key -> id map covering
    every category (top-level and child) so callers (e.g. the classifier) can resolve a key
    without a second round trip."""
    top_level_rows = [
        {"id": uuid.uuid4(), "user_id": user_id, "key": key, "label": label, "is_system": is_system}
        for key, label, is_system, _children in TAXONOMY
    ]
    await session.execute(
        insert(ActivityCategory)
        .values(top_level_rows)
        .on_conflict_do_nothing(constraint="uq_activity_categories_user_id_key")
    )

    result = await session.execute(
        select(ActivityCategory.key, ActivityCategory.id).where(ActivityCategory.user_id == user_id)
    )
    key_to_id = dict(result.all())

    child_rows = [
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "key": child_key,
            "label": child_label,
            "is_system": child_is_system,
            "parent_id": key_to_id[parent_key],
        }
        for parent_key, _parent_label, _parent_is_system, children in TAXONOMY
        for child_key, child_label, child_is_system in children
        if child_key not in key_to_id
    ]
    if child_rows:
        await session.execute(
            insert(ActivityCategory)
            .values(child_rows)
            .on_conflict_do_nothing(constraint="uq_activity_categories_user_id_key")
        )
        result = await session.execute(
            select(ActivityCategory.key, ActivityCategory.id).where(ActivityCategory.user_id == user_id)
        )
        key_to_id = dict(result.all())

    await session.commit()
    return key_to_id
