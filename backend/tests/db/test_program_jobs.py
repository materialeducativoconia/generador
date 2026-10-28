"""Official programs: searched on the web, turned into the reference syllabus, followed and checked."""

import json

from app.curriculum import Finding
from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM

PLAN = {"needed": False, "queries": [], "reason": "método práctico",
        "program_queries": ["programa SEP primer grado lectoescritura", "método de los 20 días pasos"]}
SHEET = {"program": "SEP 2022, Fase 3, Lenguajes", "method": "Silábico: vocales, luego m, p, s, l",
         "points": [{"text": "Reconoce las vocales", "source": 1}, {"text": "Lee sílabas con m", "source": 2},
                    {"text": "Dato sin fuente válida", "source": 9}]}
REVIEW = {"score": 4, "covered": ["vocales"], "missing": ["sílabas con p"], "issues": ["Falta la p"]}


class FakeSearch:
    def __init__(self):
        self.queries = []

    async def search(self, query, *, language="es"):
        self.queries.append(query)
        n = len(self.queries)
        return Finding(query, f"Hallazgo {n}", [{"title": f"Fuente {n}", "url": f"https://sep.example/{n}"}], 0.006)


async def test_the_outline_is_built_on_an_official_program_and_checked_against_it(raw_db, google_user, client, key,
                                                                                engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    search = FakeSearch()
    llm = ScriptedLLM(json.dumps(PLAN), json.dumps(SHEET), json.dumps(OUTLINE), json.dumps(REVIEW))

    await run_next(engine, llm, search=search)

    assert search.queries == PLAN["program_queries"]
    architect = llm.calls[2][-1]["content"]
    assert "Programa: SEP 2022, Fase 3" in architect and "Lee sílabas con m [programa 2]" in architect
    assert "Dato sin fuente válida" not in architect
    research = json.loads(await raw_db.fetchval("select research from public.series where id = $1", sid))
    program = research["program"]
    assert [s["url"] for s in program["sources"]] == ["https://sep.example/1", "https://sep.example/2"]
    assert program["review"]["missing"] == ["sílabas con p"] and program["cost_usd"] == 0.012

    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["research"]["program"]["program"] == "SEP 2022, Fase 3, Lenguajes"
    assert detail["research"]["program"]["findings"][0]["text"] == "Hallazgo 1"
    card = (await client.get(f"/api/series/{sid}/quality", headers=bearer(key, user))).json()
    assert card["cost"]["search_usd"] == 0.012


async def test_a_search_outage_never_blocks_the_outline(raw_db, google_user, client, key, engine):
    class DownSearch:
        async def search(self, query, *, language="es"):
            raise RuntimeError("down")

    user = await google_user()
    sid = await new_tome(client, key, user)

    await run_next(engine, ScriptedLLM(json.dumps(PLAN), json.dumps(OUTLINE)), search=DownSearch())

    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_ready"
