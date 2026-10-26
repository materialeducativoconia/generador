import asyncpg
import pytest

from tests.db.conftest import act_as, create_google_user, create_job, create_lesson, create_series


async def test_first_google_login_creates_profile_from_google_metadata(db):
    user_id = await create_google_user(db, "marta@gmail.com", "Marta Pérez", "https://lh3.googleusercontent.com/a/x")

    profile = await db.fetchrow("select * from public.profiles where id = $1", user_id)

    assert profile["email"] == "marta@gmail.com"
    assert profile["display_name"] == "Marta Pérez"
    assert profile["avatar_url"] == "https://lh3.googleusercontent.com/a/x"
    assert profile["daily_lesson_quota"] == 60
    assert profile["is_active"] is True


async def test_user_reads_own_series_lessons_jobs_and_profile(db):
    user = await create_google_user(db, "a@gmail.com")
    series = await create_series(db, user)
    await create_lesson(db, series, 1)
    await create_job(db, user, series)

    await act_as(db, "authenticated", user)

    assert await db.fetchval("select count(*) from public.series") == 1
    assert await db.fetchval("select count(*) from public.lessons") == 1
    assert await db.fetchval("select count(*) from public.generation_jobs") == 1
    assert await db.fetchval("select count(*) from public.profiles") == 1


async def test_user_cannot_see_another_users_data(db):
    owner = await create_google_user(db, "owner@gmail.com")
    intruder = await create_google_user(db, "intruder@gmail.com")
    series = await create_series(db, owner)
    await create_lesson(db, series, 1)
    await create_job(db, owner, series)
    await db.execute(
        "insert into public.exports (series_id, user_id, status, options) values ($1, $2, 'queued', '{}')", series, owner
    )

    await act_as(db, "authenticated", intruder)

    for table in ("series", "lessons", "generation_jobs", "exports"):
        assert await db.fetchval(f"select count(*) from public.{table}") == 0, table
    assert await db.fetchval("select count(*) from public.profiles where id = $1", owner) == 0


async def test_anon_sees_nothing(db):
    user = await create_google_user(db, "a@gmail.com")
    await create_series(db, user)

    await act_as(db, "anon")

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetchval("select count(*) from public.series")


async def test_generation_logs_are_invisible_even_to_their_owner(db):
    user = await create_google_user(db, "a@gmail.com")
    series = await create_series(db, user)
    job = await create_job(db, user, series)
    await db.execute(
        """
        insert into public.generation_logs (job_id, user_id, series_id, attempt, model, prompt_version, outcome)
        values ($1, $2, $3, 1, 'deepseek-chat', 'outline@1', 'ok')
        """,
        job,
        user,
        series,
    )

    await act_as(db, "authenticated", user)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetchval("select count(*) from public.generation_logs")


@pytest.mark.parametrize(
    "statement",
    [
        "insert into public.series (user_id, topic, audience, language, format, lesson_count, lesson_duration_minutes, status)"
        " values (auth.uid(), 't', '{}', 'es', 'lesson_series', 1, 45, 'outlining')",
        "update public.series set topic = 'hacked'",
        "delete from public.series",
        "update public.profiles set daily_lesson_quota = 100000",
        "update public.lessons set status = 'approved'",
    ],
)
async def test_browser_cannot_write_business_tables(db, statement):
    user = await create_google_user(db, "a@gmail.com")
    series = await create_series(db, user)
    await create_lesson(db, series, 1)

    await act_as(db, "authenticated", user)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.execute(statement)


async def test_series_rejects_more_than_20_lessons(db):
    user = await create_google_user(db, "a@gmail.com")

    with pytest.raises(asyncpg.CheckViolationError):
        await create_series(db, user, lesson_count=21)


async def test_lessons_can_swap_positions_within_one_transaction(db):
    user = await create_google_user(db, "a@gmail.com")
    series = await create_series(db, user)
    first = await create_lesson(db, series, 1)
    second = await create_lesson(db, series, 2)

    await db.execute("set constraints all deferred")
    await db.execute("update public.lessons set position = 2 where id = $1", first)
    await db.execute("update public.lessons set position = 1 where id = $1", second)
    await db.execute("set constraints all immediate")  # forces the deferred unique check now

    assert await db.fetchval("select position from public.lessons where id = $1", second) == 1


async def test_duplicate_lesson_position_is_rejected(db):
    user = await create_google_user(db, "a@gmail.com")
    series = await create_series(db, user)
    await create_lesson(db, series, 1)

    with pytest.raises(asyncpg.UniqueViolationError):
        await create_lesson(db, series, 1)


async def test_only_generation_jobs_are_published_to_realtime(db):
    tables = await db.fetch(
        "select tablename from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public'"
    )

    assert [t["tablename"] for t in tables] == ["generation_jobs"]


async def test_exports_bucket_is_private_and_pdf_only(db):
    bucket = await db.fetchrow("select public, allowed_mime_types from storage.buckets where id = 'exports'")

    assert bucket is not None
    assert bucket["public"] is False
    assert bucket["allowed_mime_types"] == ["application/pdf"]
