"""The web preview gets the very SVG the PDF prints for each diagram block."""

import json

from tests.db.test_illustrations import written_tome
from tests.db.test_jobs import engine  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer

SECTION = {"schema_version": 1, "summary": "", "blocks": [
    {"id": "b1", "type": "paragraph", "text": "El ciclo del agua"},
    {"id": "b2", "type": "cycle", "steps": ["Evaporación", "Condensación", "Precipitación"]}]}


async def test_series_and_lesson_carry_the_diagram_svg(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine, SECTION)
    await raw_db.execute("""update public.series set design = '{"theme": "ciencia", "palette": ["#F0F7FF", "#0B2545",
                            "#13A89E"], "ornament": "ninguno"}' where id = $1""", sid)

    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    lesson = detail["lessons"][0]
    single = (await client.get(f"/api/lessons/{lesson['id']}", headers=bearer(key, user))).json()

    svg = lesson["diagrams"]["b2"]
    assert svg.startswith("<svg") and "Condensación" in svg and "#13A89E" in svg and "Lexend" in svg
    assert single["diagrams"] == lesson["diagrams"] and list(lesson["diagrams"]) == ["b2"]
    assert json.dumps(lesson["content_json"]).count("<svg") == 0  # content stays pure data
