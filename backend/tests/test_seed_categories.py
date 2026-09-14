"""§15.3 default taxonomy seeding — idempotency and shape against a real Postgres."""

from sqlalchemy import select

from timeos.jobs.seed_categories import SYSTEM_LEAF_KEYS, TAXONOMY, ensure_system_categories
from timeos.models.activity_category import ActivityCategory
from timeos.models.user import User


async def _make_user(session) -> "User.id":
    user = User()
    session.add(user)
    await session.flush()
    return user.id


async def test_seeds_every_top_level_and_child_key():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user_id = await _make_user(session)
        await session.commit()
        key_to_id = await ensure_system_categories(session, user_id)

        expected_keys = {key for key, _label, _sys, _children in TAXONOMY}
        expected_keys |= {
            child_key
            for _key, _label, _sys, children in TAXONOMY
            for child_key, _child_label, _child_sys in children
        }
        assert expected_keys <= key_to_id.keys()


async def test_system_leaf_categories_are_marked_immutable():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user_id = await _make_user(session)
        await session.commit()
        await ensure_system_categories(session, user_id)

        result = await session.execute(
            select(ActivityCategory.key, ActivityCategory.is_system).where(
                ActivityCategory.user_id == user_id
            )
        )
        rows = dict(result.all())
        for key in SYSTEM_LEAF_KEYS:
            assert rows[key] is True
        assert rows["system"] is True
        assert rows["work"] is False


async def test_children_point_at_the_correct_parent():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user_id = await _make_user(session)
        await session.commit()
        key_to_id = await ensure_system_categories(session, user_id)

        result = await session.execute(
            select(ActivityCategory.key, ActivityCategory.parent_id).where(
                ActivityCategory.user_id == user_id
            )
        )
        parent_of = dict(result.all())
        assert parent_of["idle"] == key_to_id["system"]
        assert parent_of["deep_work"] == key_to_id["work"]
        assert parent_of["work"] is None  # top-level categories have no parent


async def test_running_twice_does_not_duplicate_or_reset_a_rename():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user_id = await _make_user(session)
        await session.commit()
        first = await ensure_system_categories(session, user_id)

        # Simulate a user rename of a non-system category (§15.3: everything but System is
        # user-extensible) — re-running the seed must never stomp on it.
        work = await session.get(ActivityCategory, first["work"])
        work.label = "Deep Focus Time"
        await session.commit()

        second = await ensure_system_categories(session, user_id)
        assert first == second  # same ids, no duplicates

        result = await session.execute(
            select(ActivityCategory).where(ActivityCategory.user_id == user_id)
        )
        rows = result.scalars().all()
        expected_count = sum(1 + len(children) for _k, _l, _s, children in TAXONOMY)
        assert len(rows) == expected_count

        renamed = await session.get(ActivityCategory, first["work"])
        assert renamed.label == "Deep Focus Time"
