# ARCHITECTURE.md — Generador de material educativo

> Estado: **diseño cerrado v1, revisión 2: Supabase** (2026-10-25). Ninguna línea de implementación existe todavía.
> Cada decisión con alternativas tiene su registro en [§7 Registro de decisiones](#7-registro-de-decisiones).

> **Revisión 3 (2026-10-27): tomos de cualquier género con agentes.** El usuario describe el material y el **Arquitecto** (DeepSeek) elige el género (`coloring_book`, `worksheets`, `tutorial`, `lesson_series`) y el esquema; el **Redactor** (DeepSeek) escribe cada sección con el catálogo de bloques de `backend/app/content.py` (añade `keyboard`, `tracing`, `letter_grid`, `image`, `writing_lines`, `page_break`); el **Maquetador** (código, `app/render.py`) dibuja lo exacto en SVG y genera el PDF. Fases siguientes: Ilustrador (OpenRouter) + biblioteca de imágenes compartida, Curador (Openverse/Wikimedia), Investigador (dossier con fuentes) y Revisor visual. `lessons` = secciones del tomo; `series.genre` y `series.plan` guardan la salida del Arquitecto. `GET /api/exports/{id}/file` devuelve `{url}` firmada en JSON (no 302), porque el navegador la pide con Bearer.

> **Revisión 4 (2026-10-28): Mis identidades.** Una identidad es la línea editorial del usuario (sello, lema, voz, mascota, sello gráfico + un `Design`). El job `identity` corre la **Estratega de marca** (3 líneas distintas) y la **Diseñadora de identidad** (sistema visual de cada una); el **Guardián** (`app/identity.py`, código) ajusta paletas para imprenta y evita repetir combinaciones propias o muy usadas por otros usuarios. El usuario elige una y la asigna a una **colección** (`collections.identity_id`): todos sus niveles copian el diseño (`series.identity_id`), el Redactor escribe con su voz, la mascota protagoniza portada e ilustraciones, y el PDF lleva el sello, el nombre del sello al pie y «Colección · Nivel N» en la portada.

> **Revisión 5 (2026-10-28): planes y créditos.** Planes mensuales en USD: Docente $9 (150 créditos), Creador $24 (500), Editorial $69 (1500); prueba de 40 créditos al registrarse. 1 crédito ≈ 1 página: esquema 1, portada 4, cada página 1, identidad 3, estilo 2. Plan, créditos y Stripe viven en la **organización** (`organizations`, `memberships.role`; `profiles.platform_role` para staff; `subscriptions` por app). Los créditos son bolsas (`credit_buckets`: plan, paquete, prueba) con historial en `credit_ledger`; se cobran al encolar el job y se reembolsan si falla (`app/credits.py`). Stripe (`app/stripe_gateway.py`, precios por *lookup key*, `scripts/stripe_setup.py`): Checkout, portal y webhook idempotente (`stripe_events`). Lo que incluye cada plan: `app/plans.py`.

## 0. Resumen en una página

Un docente describe una serie (tema, nivel, nº de lecciones). La app genera primero un **esquema** (títulos + objetivos por lección), el docente lo corrige y aprueba, y entonces se genera **cada lección como un bloque independiente** en paralelo, respetando el rate limit de DeepSeek. El docente revisa, edita o regenera lecciones sueltas, y exporta un **PDF maquetado** con portada, índice, lecciones y solucionario.

```
                    ┌──────────── Supabase (gestionado) ─────────────┐
                    │  Auth (JWT)   Realtime   Storage   PostgreSQL  │
                    └────▲────────────▲──────────▲───────────▲───────┘
            login/JWT    │  cambios   │          │ PDFs      │ SQL (Supavisor, session mode)
┌──────────────┐ ────────┘  de jobs   │          │           │
│ Frontend SPA │ ◀────────────────────┘          │     ┌─────┴────────┐
│ React + Vite │ ──HTTPS/JSON + Bearer JWT──────────▶  │  API FastAPI │
└──────────────┘                                 │     └──────────────┘
                              ┌──────────────┐   │           │ misma DB: datos + cola
          DeepSeek API ◀───── │    Worker    │ ──┘ ◀─────────┘ (SKIP LOCKED)
      (rate limiter global)   │ (mismo código│ ───▶ WeasyPrint
                              │  que la API) │
                              └──────────────┘          (frontend: Vercel · API + worker: Render)
```

**Stack:** React + Vite + TypeScript · **Supabase** (Postgres 16 con datos **y** cola de trabajos, Auth, Storage, Realtime) · FastAPI (Python 3.12) · un proceso worker asyncio · DeepSeek vía API directa (SDK `openai` con `base_url`) · WeasyPrint para PDF · frontend estático en **Vercel** · API (*Web Service*) + worker (*Background Worker*) en **Render**, desde la misma imagen Docker.

**Reparto de responsabilidades con Supabase** (decisión D13):

| Supabase hace | Nuestro backend hace |
|---|---|
| Registro y login **con Google** (OAuth), sesiones y renovación de tokens (Auth) | **Toda** escritura de datos de negocio: máquina de estados, cuotas, encolado |
| Hosting de Postgres, backups, pooler | Toda lectura de contenido (`/api/...`) |
| Guardar PDFs en un bucket privado y firmar URLs de descarga (Storage) | Llamadas a DeepSeek y render de PDF (worker) |
| Avisar al navegador cuando cambia un job (Realtime) | Autorización: verifica el JWT de Supabase en cada request |

El navegador usa `supabase-js` **solo** para Auth y Realtime. No lee ni escribe tablas de negocio directamente.

Tres principios guían todo el diseño:

1. **Nada lento ocurre dentro de una request HTTP.** Toda llamada a DeepSeek y toda generación de PDF es un *job* en la cola. La API solo encola y responde `202`. Lo mismo vale para Supabase: nada lento corre en Edge Functions.
2. **El esquema es el contrato.** Las lecciones se generan en paralelo y sin verse entre sí; la coherencia de la serie la garantiza el esquema aprobado, que viaja en el prompt de cada lección.
3. **El contenido es JSON estructurado, nunca HTML ni Markdown libre.** El mismo `content_json` alimenta el editor del frontend y la plantilla del PDF, y se valida con un schema antes de guardarse.

---

## 1. El momento del usuario

Persona: **Marta, profesora de Ciencias de 2º de secundaria**, quiere una secuencia de 10 lecciones sobre "El ciclo del agua y el cambio climático" para el próximo trimestre.

### Paso 0 — Entrar (pantalla "Bienvenida")

Un único botón: **"Continuar con Google"**. No hay formulario de registro ni contraseña.

- Primera vez: Google pide consentimiento para compartir nombre, email y foto, y Marta vuelve a la app **ya registrada**. Su nombre de Google rellena "Elaborado por…" en la portada del PDF, y puede cambiarlo en su perfil.
- Las siguientes veces: si ya tiene sesión de Google en el navegador, entrar es un clic.
- Sirve **cualquier cuenta de Google**: `@gmail.com` o la cuenta de su centro (Google Workspace for Education).

### Paso 1 — Input (pantalla "Nueva serie")

Rellena un formulario corto. Solo el tema es obligatorio; el resto tiene valores por defecto.

| Campo | Ejemplo | Default |
|---|---|---|
| Tema | El ciclo del agua y el cambio climático | — |
| Nivel / curso | Secundaria · 2º (13–14 años) | — |
| Nº de lecciones | 10 | 10 (rango 1–20) |
| Duración por lección | 50 min | 45 |
| Formato | Serie de lecciones · Cuadernillo del alumno | Serie de lecciones |
| Idioma | Español | Idioma de la UI |
| Instrucciones extra | "Incluir un experimento casero por lección" | vacío |

Pulsa **"Generar esquema"**. La UI pasa al estado *Generando esquema…* (normalmente tarda 10–30 s).

### Paso 2 — Esquema (pantalla "Esquema")

Ve 10 tarjetas, cada una con un título, de 2 a 4 objetivos de aprendizaje y de 3 a 5 conceptos clave. Puede:

- editar cualquier texto en línea,
- reordenar (arrastrar), añadir o eliminar lecciones,
- **"Regenerar esquema"** con una instrucción ("menos teoría, más práctica en las lecciones 6–10").

Nada se genera hasta que pulsa **"Aprobar y generar lecciones"**. Este es el punto de control más barato: corregir un esquema cuesta una llamada; corregir 10 lecciones mal enfocadas cuesta diez.

### Paso 3 — Generación por bloques (pantalla "Serie")

Las 10 tarjetas pasan a *En cola* y luego, de forma independiente, a *Generando* y *Lista*. Cada lección es un bloque: una llamada a DeepSeek → un `content_json` validado.

- Puede abrir y leer la lección 1 mientras la 7 aún se genera.
- Si una lección falla (tras los reintentos automáticos), su tarjeta muestra *Error* con un botón **"Reintentar"**. Un fallo **no** bloquea al resto.
- Puede cerrar el navegador: la generación sigue en el servidor.

### Paso 4 — Revisión (pantalla "Lección")

La lección se muestra con el mismo orden y jerarquía que tendrá en el PDF: introducción, explicación, ejemplos, actividad, ejercicios y clave de respuestas. Por cada lección puede:

- **Editar** un bloque concreto (párrafo, ejercicio, tabla…).
- **Regenerar la lección** o **regenerar un bloque** con una instrucción ("haz el experimento con materiales más baratos").
- **Marcar como revisada** ✓. Es opcional; la pantalla de serie muestra "7/10 revisadas" como checklist.

### Paso 5 — PDF (diálogo "Exportar")

Elige la plantilla (`clásica` en v1), el tamaño de papel (A4 o Carta) y si incluye el solucionario al final. Pulsa **"Generar PDF"**: en 5–30 s aparece **"Descargar"** y una vista previa embebida. Las exportaciones anteriores quedan en el historial de la serie.

Para exportar, todas las lecciones deben estar en `generated`, `edited` o `approved`. Si hay alguna sin revisar, se muestra un aviso, pero la exportación no se bloquea.

---

## 2. Flujo de datos end-to-end

### 2.1 Los saltos, en orden

```
 [0] Browser ──signInWithOAuth({provider:'google'}) (PKCE)──▶ Supabase Auth ──302──▶ Google (consentimiento)
     Google ──302 + code──▶ Supabase Auth /auth/v1/callback ──302──▶ app /auth/callback?code=…
     Browser ──intercambia code (supabase-js)──▶ Supabase Auth ──access token (JWT) + refresh token──▶ Browser
 [1] Browser ──POST /api/series + Authorization: Bearer <JWT>──▶ API (verifica JWT con JWKS)
 [2] API ──INSERT series + job(outline) en 1 transacción──▶ Supabase Postgres ──202──▶ Browser
 [3] Worker ──SELECT … FOR UPDATE SKIP LOCKED──▶ Supabase Postgres   (toma el job)
 [4] Worker ──chat.completions (stream, JSON mode)──▶ DeepSeek
 [5] Worker ──valida JSON (Pydantic) ──▶ UPDATE lessons/series/job + INSERT generation_log──▶ Supabase Postgres
 [6] Supabase Realtime ──postgres_changes (generation_jobs, filtrado por series_id, con RLS)──▶ Browser
     Browser ──GET /api/series/{id}/progress──▶ API   (el evento solo avisa; el dato se pide a la API)
        … el usuario aprueba el esquema: [1]–[6] se repiten con N jobs `lesson` …
 [7] Browser ──POST /api/series/{id}/exports──▶ API ──job(pdf_export)──▶ Supabase Postgres
 [8] Worker ──content_json → Jinja2 → HTML+CSS──▶ WeasyPrint ──PDF bytes
 [9] Worker ──upload (service role)──▶ Supabase Storage, bucket privado `exports` ; UPDATE exports
[10] Browser ──GET /api/exports/{id}/file──▶ API ──302 a URL firmada (60 s)──▶ Supabase Storage ──PDF──▶ Browser
```

### 2.2 Dónde puede fallar cada salto y qué hacemos

| Salto | Fallo posible | Detección | Respuesta del sistema |
|---|---|---|---|
| **[1] Browser → API** | Doble clic / reenvío → series duplicadas | Header `Idempotency-Key` | La API guarda la clave 24 h y devuelve la misma respuesta sin crear nada nuevo |
| **[0]/[1] Auth** | Access token expirado (TTL ~1 h) | `401` de la API | `supabase-js` lo renueva solo con el refresh token; el cliente HTTP reintenta **una vez** tras `refreshSession()`. Si vuelve a fallar → login, conservando el borrador del formulario en `localStorage` |
| | JWKS de Supabase inaccesible | Error al obtener las claves | La API cachea el JWKS en memoria (10 min) y sigue validando con las claves cacheadas |
| **[0] Google OAuth** | El usuario cancela en la pantalla de Google | `/auth/callback?error=access_denied` | Vuelve a "Bienvenida" con el mensaje "No se completó el inicio de sesión", sin tratarlo como error |
| | `redirect_uri_mismatch` o redirect no permitido | Error de Google o de Supabase en el callback | Error de configuración, no del usuario. Se evita con la lista de URLs por entorno (§5.2c) y un test E2E de login en staging |
| | El administrador de Google Workspace del centro bloquea apps de terceros | Google muestra "Acceso bloqueado" (`admin_policy_enforced`) | **Riesgo real para docentes.** Mitigación: pantalla de consentimiento con la marca **verificada** por Google, y una página de ayuda con el *client ID* para que el admin del centro autorice la app. Alternativa del usuario: entrar con una cuenta `@gmail.com` personal |
| | El *code* PKCE se intercambia en otra pestaña o navegador | Error al intercambiar el code | Se reinicia el login. El `code_verifier` vive en el `localStorage` del navegador que inició el flujo |
| | Input inválido (20+ lecciones, tema vacío) | Validación Pydantic | `422` con `error.details` por campo |
| | Cuota diaria del usuario agotada | Contador en `generation_jobs` | `429 quota_exceeded`. Protege la factura de DeepSeek frente a abuso |
| **[2] API → DB** | Crash entre crear la serie y encolar el job | — | Imposible por diseño: serie y job se insertan **en la misma transacción** (la cola vive en la misma base) |
| | Pooler de Supabase saturado / límite de conexiones del plan | Timeout al adquirir conexión | Pools pequeños y fijos (API 10, worker 5) en **session mode**. Ver §5.2b |
| | Proyecto de Supabase pausado (plan Free tras ~7 días sin actividad) | Conexión rechazada | **Producción en plan Pro**, que no se pausa. Free solo para desarrollo |
| **[3] Worker toma job** | El worker muere con un job a medias | `locked_at` más antiguo que el *lease* (10 min) | Un *reaper* lo devuelve a `queued` e incrementa `attempts` |
| | Dos workers toman el mismo job | — | Imposible: `FOR UPDATE SKIP LOCKED` |
| **[4] Worker → DeepSeek** | **Rate limit (60 RPM asumido)** → `429` | Status HTTP | **Prevención:** token bucket global a **50 RPM** (margen del 17 %) + máx. **16 llamadas en vuelo**. **Reacción:** backoff exponencial con jitter (2 s, 4 s, 8 s, 16 s), respetando `Retry-After` si viene |
| | Servidor saturado → `500` / `503` | Status HTTP | Mismo backoff; máx. 4 intentos y luego `failed` con `error_code=upstream_unavailable` |
| | Llamada lenta: una lección de ~5k tokens tarda 60–150 s; con la API cargada, DeepSeek retiene la conexión antes de empezar | Streaming + timeouts | **Streaming interno** (el usuario no lo ve): timeout de *inactividad* de 90 s entre chunks y techo total de 10 min. Así se distingue "lento pero vivo" de "colgado" |
| | `401` (key inválida) / `402` (saldo insuficiente) | Status HTTP | **Sin reintento.** Se pausa la cola completa (`queue_paused` en config) y se alerta al operador: reintentar solo quemaría intentos |
| | JSON malformado o contenido vacío | `json.loads` / Pydantic | 1 reintento de **reparación**: se reenvía el error de validación pidiendo corregir. Si vuelve a fallar → `failed`, `error_code=invalid_output` |
| | Salida truncada (`finish_reason == "length"`) | Campo `finish_reason` | Reintento con `max_tokens` al máximo del modelo. Si aún trunca → `failed`, `error_code=too_long`; la UI sugiere dividir la lección |
| | Contenido válido pero incorrecto (idioma equivocado, pocos ejercicios) | Validación semántica post-schema (idioma detectado, ≥ N ejercicios, objetivos cubiertos) | Igual que JSON inválido: 1 reintento de reparación |
| **[5] Worker → DB** | Usuario edita la lección mientras se regenera | Columna `content_version` | El worker escribe solo si `content_version` no cambió desde que encoló; si cambió, el resultado se guarda como **propuesta** (`pending_content_json`) que el usuario acepta o descarta |
| **[6] Realtime** | Usuario cierra la pestaña | — | Irrelevante: el estado vive en la DB. Al volver se pide `/progress` y se re-suscribe |
| | Se cae el websocket de Realtime y se pierden eventos | Estado del canal en `supabase-js` (`CHANNEL_ERROR`, `TIMED_OUT`, `CLOSED`) | Al reconectar **siempre** se pide `/progress` completo (Realtime es una señal, no la fuente de verdad). Además hay un *polling de seguridad* cada 15 s **solo mientras haya jobs activos** |
| | Política RLS mal escrita → el usuario recibe eventos de otro | Test automatizado de RLS (§5.5) | Los eventos solo traen IDs y estados; el contenido siempre se pide a la API, que vuelve a autorizar |
| **[8] WeasyPrint** | Serie enorme → lento o mucha RAM | Timeout de 120 s por export; límite de memoria del contenedor | `failed`, `error_code=render_timeout`. Límite duro: 20 lecciones por serie |
| | Fuente no instalada → tipografía de reserva fea | Test de humo en CI que renderiza un PDF y verifica las fuentes embebidas | Las fuentes van **dentro de la imagen Docker**, nunca por URL |
| | HTML/CSS inyectado por el LLM, o SSRF vía `<img src="http://…">` | — | Jinja2 con **autoescape**; el LLM nunca produce HTML, solo JSON. `url_fetcher` de WeasyPrint restringido a `file://` en el directorio de assets |
| **[9] Storage** | Fallo al subir | Excepción del SDK | Reintento ×3; si falla, job `failed`. El PDF se regenera de forma determinista a partir de la DB |
| | PDF mayor que el límite de subida | Tamaño antes de subir | Límite global del proyecto ≥ 50 MB; una serie de 20 lecciones sin imágenes ronda 1–5 MB |
| **[10] Descarga** | Archivo inexistente | `404` | La UI ofrece "Volver a generar" |
| | URL firmada caducada (el usuario tardó en hacer clic) | `400`/`403` de Storage | La URL se pide **en el momento del clic** (`/file` → 302), nunca se guarda en la UI |

### 2.3 Presupuesto de rate limit

- Una serie de 10 lecciones = 1 (esquema) + 10 (lecciones) = **11 requests**, muy por debajo de 60 RPM.
- El límite importa con concurrencia: 6 docentes aprobando su esquema en el mismo minuto = 60 requests. El token bucket las **escalona**; nadie recibe un `429`, simplemente tarda un poco más.
- El cuello de botella real son las **llamadas en vuelo** (cada una dura ~1–2 min). Con 16 en vuelo y ~90 s por lección, el sistema produce unas **10 lecciones/min**, unas 600/h. Suficiente para v1.
- **Nota:** DeepSeek no publica un RPM fijo; su límite es dinámico según la carga del servicio. El valor de 60 RPM es una **suposición de diseño** y va en config (`DEEPSEEK_RPM=50`, `DEEPSEEK_MAX_INFLIGHT=16`), no en código.

### 2.4 Aprovechar la caché de contexto de DeepSeek

DeepSeek cachea automáticamente los **prefijos** repetidos de los prompts, y los tokens de entrada que coinciden con la caché se cobran más baratos. Por eso el prompt de cada lección se ordena **de lo más estable a lo más variable**:

```
[system]  instrucciones fijas + schema de content_json          ← idéntico para todos
[user]    datos de la serie + ESQUEMA COMPLETO aprobado         ← idéntico para las 10 lecciones
[user]    "Genera ahora la lección {n}: {título}, {objetivos}"   ← lo único que cambia
```

Las lecciones 2 a 10 aprovechan la caché de todo el prefijo. `generation_logs` registra `prompt_cache_hit_tokens` para comprobarlo.

---

## 3. Contratos de API

### Convenciones

- Base: `/api`, JSON UTF-8, IDs como UUID v7 (ordenables por tiempo).
- Auth: **Supabase Auth con Google como único proveedor**. El frontend obtiene el access token con `supabase-js` y lo manda como `Authorization: Bearer <JWT>`. La API lo verifica **localmente** contra el JWKS del proyecto (`https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`; el proyecto se configura con *signing keys* asimétricas), comprobando `exp`, `iss` y `aud = "authenticated"`. El `sub` del token es el `user_id`. Frontend y API comparten dominio: un *rewrite* de Vercel envía `/api/*` a la API en Render, así que no hay CORS. Como no hay cookie de sesión, tampoco hay CSRF.
- Los endpoints que encolan trabajo responden **`202 Accepted`** con el job creado y aceptan el header `Idempotency-Key`.
- Escrituras sobre recursos editables usan **concurrencia optimista**: el cliente envía `version`; si no coincide → `409 version_conflict`.
- Error uniforme:

```json
{ "error": { "code": "version_conflict", "message": "La lección fue modificada en otra pestaña.", "details": { "current_version": 4 } } }
```

Códigos: `validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `version_conflict` (409), `invalid_state` (409, p. ej. aprobar un esquema que aún se genera), `quota_exceeded` (429).

### Mapa de endpoints

| Método | Ruta | Qué hace | Respuesta |
|---|---|---|---|
| — | *(registro/login con Google, logout)* | Los hace `supabase-js` (`signInWithOAuth`, `signOut`) contra Supabase Auth; **no existen en nuestra API** | — |
| PATCH | `/api/me` | Cambia `display_name` (nombre en la portada) | 200 |
| GET | `/api/health` | Health check de Render (sin auth): `200` si la DB responde | 200 / 503 |
| GET | `/api/me` | Perfil (`profiles`) + cuota restante | 200 |
| POST | `/api/series` | Crea serie y **encola el esquema** | 202 |
| GET | `/api/series` | Lista las series del usuario | 200 |
| GET | `/api/series/{id}` | Serie + lecciones (sin `content_json`) | 200 |
| GET | `/api/series/{id}/progress` | Estado compacto (se pide al llegar un evento de Realtime) | 200 |
| PATCH | `/api/series/{id}/outline` | Edita el esquema | 200 |
| POST | `/api/series/{id}/outline/regenerate` | Regenera el esquema con instrucción | 202 |
| POST | `/api/series/{id}/lessons/generate` | **Aprueba el esquema** y encola lecciones | 202 |
| GET | `/api/lessons/{id}` | Lección completa | 200 |
| PATCH | `/api/lessons/{id}` | Edición manual de contenido | 200 |
| POST | `/api/lessons/{id}/regenerate` | Regenera la lección o un bloque | 202 |
| POST | `/api/lessons/{id}/approve` | Marca como revisada | 200 |
| POST | `/api/series/{id}/exports` | Encola un PDF | 202 |
| GET | `/api/exports/{id}` | Estado del export | 200 |
| GET | `/api/exports/{id}/file` | Redirige a una URL firmada de Supabase Storage | 302 |

> **Desviación consciente respecto a la propuesta inicial:** `GET /api/export/pdf` se sustituye por `POST /api/series/{id}/exports` + `GET /api/exports/{id}/file`. Un GET que tarda 30 s, puede fallar y crea un artefacto no es idempotente ni cacheable, y además choca con los timeouts de proxies. `POST /api/lessons/generate` pasa a colgar de la serie (`/api/series/{id}/lessons/generate`) porque aprobar el esquema es una transición de estado **de la serie**.

### 3.1 `POST /api/series`

Request:

```json
{
  "topic": "El ciclo del agua y el cambio climático",
  "audience": { "stage": "secundaria", "grade": "2º", "age_range": [13, 14] },
  "lesson_count": 10,
  "lesson_duration_minutes": 50,
  "format": "lesson_series",
  "language": "es",
  "extra_instructions": "Incluir un experimento casero por lección"
}
```

`format` ∈ `lesson_series` (guía docente) | `workbook` (cuadernillo del alumno: menos exposición, más ejercicios con espacio para responder).

Response `202`:

```json
{
  "series": {
    "id": "0192f1c4-7a10-7c3e-9b1a-3f0e2d1c0a01",
    "title": null,
    "status": "outlining",
    "lesson_count": 10,
    "version": 1,
    "created_at": "2026-10-25T10:00:00Z"
  },
  "job": { "id": "0192f1c4-7a11-7d00-8000-000000000001", "kind": "outline", "status": "queued" }
}
```

### 3.2 `GET /api/series/{id}/progress`

Se llama al abrir la serie, cada vez que llega un evento de Realtime sobre un job de la serie (con *debounce* de 500 ms, porque 10 lecciones terminando a la vez no deben disparar 10 requests) y al reconectar el websocket. Es pequeño, sin contenido, y se sirve con un único query indexado.

Suscripción en el frontend (pseudocódigo):

```ts
supabase.channel(`series:${id}`)
  .on('postgres_changes',
      { event: '*', schema: 'public', table: 'generation_jobs', filter: `series_id=eq.${id}` },
      () => debouncedRefetchProgress())
  .subscribe(status => { if (status === 'SUBSCRIBED') refetchProgress() })
```

```json
{
  "series_id": "0192f1c4-…a01",
  "status": "generating",
  "counts": { "total": 10, "pending": 0, "queued": 3, "generating": 4, "generated": 2, "failed": 1, "edited": 0, "approved": 0 },
  "lessons": [
    { "id": "…b01", "position": 1, "status": "generated", "updated_at": "2026-10-25T10:03:12Z" },
    { "id": "…b02", "position": 2, "status": "failed", "error": { "code": "invalid_output", "message": "El modelo devolvió JSON inválido dos veces." } },
    { "id": "…b03", "position": 3, "status": "generating" }
  ],
  "poll_after_ms": 2000
}
```

`poll_after_ms` controla solo el *polling de seguridad* (15 s por defecto, y solo con jobs activos); el servidor puede subirlo bajo carga.

### 3.3 `PATCH /api/series/{id}/outline`

Solo válido en `status = outline_ready`. Reemplaza la lista completa: el orden del array es el orden de las lecciones; un objeto sin `id` es una lección nueva y las lecciones omitidas se eliminan.

```json
{
  "version": 2,
  "title": "El agua que nos rodea",
  "lessons": [
    { "id": "…b01", "title": "¿Dónde está el agua de la Tierra?", "objectives": ["Identificar los principales depósitos de agua", "Estimar proporciones agua dulce / salada"], "key_points": ["hidrosfera", "acuíferos", "glaciares"] },
    { "title": "Nueva lección: el agua en mi ciudad", "objectives": ["Trazar el recorrido del agua del grifo"], "key_points": ["potabilización"] }
  ]
}
```

Response `200`: la serie completa con `version: 3`.

### 3.4 `POST /api/series/{id}/lessons/generate`

Transición `outline_ready → generating`. Sin body (o `{}`), encola todas las lecciones en `pending`. Con `lesson_ids`, solo esas; se usa también para **reintentar las fallidas**.

```json
{ "lesson_ids": ["…b02"] }
```

Response `202`:

```json
{
  "series": { "id": "…a01", "status": "generating", "version": 4 },
  "jobs": [ { "id": "…j02", "kind": "lesson", "lesson_id": "…b02", "status": "queued" } ]
}
```

### 3.5 `GET /api/lessons/{id}`

```json
{
  "id": "…b01",
  "series_id": "…a01",
  "position": 1,
  "title": "¿Dónde está el agua de la Tierra?",
  "objectives": ["Identificar los principales depósitos de agua", "Estimar proporciones agua dulce / salada"],
  "status": "generated",
  "content_version": 1,
  "content_json": { "schema_version": 1, "duration_minutes": 50, "summary": "…", "blocks": [ "…ver §4.3…" ] },
  "pending_content_json": null,
  "updated_at": "2026-10-25T10:03:12Z"
}
```

### 3.6 `PATCH /api/lessons/{id}`

Edición manual. Envía el `content_json` completo, que se valida con el mismo schema que la salida del LLM. Pasa el estado a `edited`.

```json
{ "content_version": 1, "title": "¿Dónde está el agua?", "objectives": ["…"], "content_json": { "schema_version": 1, "blocks": [ "…" ] } }
```

Response `200` con `content_version: 2`, o `409 version_conflict`.

### 3.7 `POST /api/lessons/{id}/regenerate`

```json
{ "instructions": "El experimento debe usar materiales que cuesten menos de 2 €", "block_id": "b7" }
```

Sin `block_id` → regenera la lección completa. Con `block_id` → regenera solo ese bloque: el prompt incluye la lección entera como contexto y pide **un único bloque** con el mismo `type`. Response `202` `{ "job": { … } }`.

Si la lección está en `edited` o `approved`, el resultado no la sobrescribe: llega como `pending_content_json` y la UI muestra un diff con **"Aceptar" / "Descartar"**. El trabajo manual del docente nunca se pierde en silencio.

### 3.8 `POST /api/series/{id}/exports`

```json
{ "template": "classic", "paper": "A4", "include_answer_key": true, "include_cover": true, "include_toc": true }
```

Response `202`:

```json
{ "export": { "id": "…e01", "status": "queued", "created_at": "2026-10-25T10:20:00Z" } }
```

Si ya existe un export `succeeded` con el mismo `content_hash` (hash de todas las lecciones + opciones), la API devuelve **ese** export con `200` sin volver a renderizar.

### 3.9 `GET /api/exports/{id}`

```json
{
  "id": "…e01",
  "status": "succeeded",
  "page_count": 64,
  "size_bytes": 1843200,
  "download_url": "/api/exports/…e01/file",
  "created_at": "2026-10-25T10:20:00Z",
  "finished_at": "2026-10-25T10:20:14Z"
}
```

`GET /api/exports/{id}/file` → la API verifica que el export pertenece al usuario, pide a Supabase Storage una **URL firmada de 60 s** (`create_signed_url(storage_key, 60, download="el-agua-que-nos-rodea.pdf")`) y responde `302 Location: <url>`. El PDF no pasa por nuestro servidor, y la URL se genera en cada clic, así que nunca caduca en la UI. El bucket `exports` es **privado**: no tiene políticas de lectura para `authenticated`; solo el service role del worker sube y solo la API firma.

---

## 4. Modelo de datos

Supabase Postgres (schema `public`), accedido desde Python con SQLAlchemy 2.0 (async, asyncpg). **El esquema lo definen las migraciones SQL de Supabase CLI** (`supabase/migrations/*.sql`), no Alembic, porque además de tablas incluyen políticas RLS, la publicación de Realtime, buckets de Storage y el trigger de perfiles (D15). Todas las tablas tienen `created_at` y `updated_at` (`timestamptz`). Los IDs de negocio son `uuid` v7, generados en Python.

### 4.1 Diagrama

```
auth.users (Supabase) 1───1 profiles
                              │
                              1
                              │
                              *
series 1───* lessons
  │  1         │ 1
  │            │
  *            *
generation_jobs 1───* generation_logs
  │
series 1───* exports ──(1:1 opcional)── generation_jobs(kind=pdf_export)
```

### 4.2 Tablas

**`auth.users`** — tabla de **Supabase Auth**. Guarda el email, la identidad de Google (`auth.identities`) y las sesiones. No la tocamos ni la extendemos. No hay contraseñas.

**`profiles`** — nuestro "User"; 1:1 con `auth.users`

| Columna | Tipo | Notas |
|---|---|---|
| id | uuid PK, FK → `auth.users(id)` ON DELETE CASCADE | mismo id que el usuario de Auth (`sub` del JWT) |
| email | text NOT NULL | copia del email de Google, para mostrarlo y para soporte |
| display_name | text | inicial: nombre de Google; editable. Aparece en la portada del PDF ("Elaborado por…") |
| avatar_url | text | foto de Google, solo para la UI; nunca se incrusta en el PDF |
| daily_lesson_quota | int NOT NULL DEFAULT 60 | lecciones generables por día (incluye regeneraciones) |
| is_active | bool NOT NULL DEFAULT true | la API rechaza con `403` si es false (bloqueo sin borrar la cuenta) |

Un trigger `AFTER INSERT ON auth.users` (función `SECURITY DEFINER`) crea la fila de `profiles` en el primer login con Google. Esa es la "alta" de la cuenta. El trigger copia `email`, `raw_user_meta_data->>'full_name'` → `display_name` y `raw_user_meta_data->>'avatar_url'` → `avatar_url`. Si Google cambia el nombre después, **no** se sobrescribe `display_name`, porque el docente pudo haberlo personalizado. Las FK `user_id` del resto de tablas apuntan a `profiles(id)`.

**`series`**

| Columna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → profiles NOT NULL | índice |
| title | text | null hasta que llega el esquema |
| topic | text NOT NULL | |
| audience | jsonb NOT NULL | `{stage, grade, age_range}` |
| language | text NOT NULL | BCP-47, `es` |
| format | enum `lesson_series` \| `workbook` | |
| lesson_count | smallint NOT NULL | 1–20 (CHECK) |
| lesson_duration_minutes | smallint NOT NULL | |
| extra_instructions | text | |
| status | enum (ver §4.4) NOT NULL | |
| outline_approved_at | timestamptz | |
| version | int NOT NULL DEFAULT 1 | concurrencia optimista del esquema |

**`lessons`**

| Columna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| series_id | uuid FK → series ON DELETE CASCADE | |
| position | smallint NOT NULL | UNIQUE (series_id, position) DEFERRABLE, para poder reordenar en una transacción |
| title | text NOT NULL | |
| objectives | jsonb NOT NULL | `["…", "…"]` |
| key_points | jsonb NOT NULL | conceptos del esquema; entran en el prompt |
| content_json | jsonb | null hasta que se genera; schema §4.3 |
| pending_content_json | jsonb | propuesta de regeneración sobre contenido editado |
| status | enum (ver §4.4) NOT NULL | índice (series_id, status) |
| content_version | int NOT NULL DEFAULT 0 | +1 en cada escritura de `content_json` |
| last_error | jsonb | `{code, message}` del último fallo |
| approved_at | timestamptz | |

**`generation_jobs`** — la cola y la fuente del estado que muestra la UI

| Columna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK NOT NULL | para cuotas |
| series_id | uuid FK NOT NULL | |
| lesson_id | uuid FK NULL | null en `outline` y `pdf_export` |
| kind | enum `outline` \| `lesson` \| `lesson_block` \| `pdf_export` | |
| status | enum `queued` \| `running` \| `succeeded` \| `failed` \| `cancelled` | |
| payload | jsonb NOT NULL | instrucciones, `block_id`, `expected_content_version`, opciones de export |
| attempts | smallint NOT NULL DEFAULT 0 | |
| max_attempts | smallint NOT NULL DEFAULT 4 | |
| run_after | timestamptz NOT NULL DEFAULT now() | backoff = reprogramar `run_after` |
| locked_at / locked_by | timestamptz / text | lease del worker |
| error | jsonb | |
| idempotency_key | text | UNIQUE (user_id, idempotency_key) |
| finished_at | timestamptz | |

Índice parcial para que la cola sea O(log n): `CREATE INDEX ON generation_jobs (run_after) WHERE status = 'queued';`

**`generation_logs`** — una fila **por llamada HTTP a DeepSeek** (un job con reintentos tiene varias)

| Columna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| job_id | uuid FK → generation_jobs | |
| user_id, series_id, lesson_id | uuid | desnormalizados para analítica sin joins |
| attempt | smallint | |
| model | text | p. ej. `deepseek-chat` |
| prompt_version | text | p. ej. `lesson@3`; los prompts viven versionados en el repo |
| request_messages | jsonb | prompt completo (**retención 30 días**, luego se pone a null) |
| response_text | text | salida cruda, aunque sea inválida (retención 30 días) |
| finish_reason | text | `stop` \| `length` \| … |
| prompt_tokens, completion_tokens | int | |
| prompt_cache_hit_tokens, prompt_cache_miss_tokens | int | reportados por DeepSeek en `usage` |
| cost_usd_micros | bigint | calculado con la tabla de precios en config en el momento de la llamada |
| latency_ms, time_to_first_token_ms | int | |
| http_status | smallint | |
| outcome | enum `ok` \| `rate_limited` \| `upstream_error` \| `timeout` \| `invalid_output` \| `truncated` \| `auth_error` | |

**`exports`**: `id`, `series_id` FK, `user_id` FK, `job_id` FK, `status`, `options` jsonb, `content_hash` text (índice), `storage_key` text (ruta en el bucket: `{user_id}/{series_id}/{export_id}.pdf`), `page_count`, `size_bytes`, `finished_at`.

### 4.2b Row Level Security y Realtime

**RLS activado en todas las tablas de `public`, sin excepción.** Supabase expone `public` vía PostgREST con la *anon key*, que es pública porque va en el frontend, así que una tabla sin RLS quedaría legible para cualquiera.

| Tabla | Política para `authenticated` | Motivo |
|---|---|---|
| `profiles` | `SELECT` donde `id = auth.uid()` | |
| `series` | `SELECT` donde `user_id = auth.uid()` | |
| `lessons` | `SELECT` donde exista la `series` padre con `user_id = auth.uid()` | |
| `generation_jobs` | `SELECT` donde `user_id = auth.uid()` | **necesaria para Realtime**, que aplica RLS a cada evento |
| `exports` | `SELECT` donde `user_id = auth.uid()` | |
| `generation_logs` | **ninguna**: invisible | contiene prompts y respuestas crudas |

- **Ninguna política de `INSERT/UPDATE/DELETE`** para `authenticated` o `anon`: todas las escrituras pasan por nuestra API. Las políticas de `SELECT` existen para Realtime y como defensa en profundidad, no porque el frontend lea tablas.
- La API y el worker conectan con un rol de servidor (`postgres` o un rol dedicado con `BYPASSRLS`). Esa credencial y la *service role key* **nunca** salen del servidor. La autorización de la API se hace en código: cada query filtra por el `user_id` del JWT.
- **Realtime:** solo `generation_jobs` se añade a la publicación `supabase_realtime`. Sus filas son pequeñas (sin `content_json`), así que los eventos son ligeros y no chocan con el límite de tamaño de payload.

### 4.3 Schema de `content_json` (v1)

El LLM devuelve exactamente esto (JSON mode). Se valida con un modelo Pydantic, que es la **única fuente de verdad**: de él se exporta un JSON Schema que se incluye en el prompt y genera los tipos TypeScript del frontend.

```json
{
  "schema_version": 1,
  "duration_minutes": 50,
  "summary": "En esta lección el alumnado descubre que solo el 2,5 % del agua del planeta es dulce…",
  "blocks": [
    { "id": "b1", "type": "heading", "level": 2, "text": "Introducción" },
    { "id": "b2", "type": "paragraph", "text": "¿Alguna vez te has preguntado **de dónde** sale el agua del grifo?" },
    { "id": "b3", "type": "callout", "variant": "key_idea", "title": "Idea clave", "text": "…" },
    { "id": "b4", "type": "list", "style": "bullet", "items": ["Océanos: 97,5 %", "Glaciares: 1,7 %"] },
    { "id": "b5", "type": "table", "caption": "Depósitos de agua", "headers": ["Depósito", "%"], "rows": [["Océanos", "97,5"]] },
    { "id": "b6", "type": "example", "title": "Ejemplo", "text": "…" },
    { "id": "b7", "type": "activity", "title": "Experimento: ciclo del agua en una bolsa", "duration_minutes": 15, "materials": ["bolsa zip", "agua", "cinta"], "steps": ["…", "…"] },
    { "id": "b8", "type": "exercise", "kind": "multiple_choice", "prompt": "¿Qué porcentaje del agua es dulce?", "options": ["2,5 %", "25 %", "50 %"], "answer": "2,5 %", "explanation": "…", "answer_space_lines": 0 },
    { "id": "b9", "type": "exercise", "kind": "open", "prompt": "Explica con tus palabras…", "answer": "Respuesta modelo: …", "answer_space_lines": 5 }
  ]
}
```

Reglas:

- `type` ∈ `heading | paragraph | list | callout | table | example | activity | exercise`. Un tipo desconocido falla la validación.
- `exercise.kind` ∈ `open | multiple_choice | true_false | fill_blank`. Los campos `answer` y `explanation` alimentan el **solucionario** y nunca se renderizan en el cuerpo del alumno.
- **Formato en línea:** solo `**negrita**` y `*cursiva*`, parseado en el servidor **después** de escapar HTML. No se admiten enlaces, imágenes ni HTML.
- Validación semántica tras el schema: ≥ 1 `activity`, ≥ 3 `exercise`, IDs de bloque únicos, idioma correcto. En `workbook`, ≥ 6 ejercicios con `answer_space_lines`.
- `schema_version` permite migrar el contenido guardado si el schema evoluciona.

### 4.4 Máquinas de estados

**Series**

```
outlining ──ok──▶ outline_ready ──approve──▶ generating ──todas listas──▶ ready
    │                 ▲    │                     │  ▲
    └──fallo──▶ outline_failed  └─regenerate─▶ outlining   └──alguna failed──▶ needs_attention ─retry─┘
```

- `ready` = todas las lecciones en `generated | edited | approved`, sin jobs activos. Es el único estado que permite exportar.
- `needs_attention` = no hay jobs activos, pero alguna lección está en `failed`.
- El estado de la serie se **recalcula** a partir de sus lecciones en la misma transacción en que el worker escribe una lección. Nunca se fija a mano.

**Lesson**

```
pending ─▶ queued ─▶ generating ─▶ generated ─edit─▶ edited ─approve─▶ approved
                        │              ▲  │                │               │
                        └─▶ failed ─retry─┘  └──── regenerate (vuelve a queued; si edited/approved → pending_content_json) ──┘
```

---

## 5. Stack técnico

### 5.1 Decisión: **React (Vite) SPA + Supabase + FastAPI + worker Python**

| Capa | Elección | Por qué *para este caso* |
|---|---|---|
| Frontend | React 19 + Vite + TypeScript, React Router, TanStack Query, Tailwind + shadcn/ui, dnd-kit (reordenar esquema), `@supabase/supabase-js` (solo Auth + Realtime) | Es una app detrás de login: no hay SEO ni páginas públicas que justifiquen SSR. TanStack Query cachea el estado del servidor y los eventos de Realtime simplemente invalidan sus queries. Se compila a estáticos y se sirve desde **Vercel** (CDN, previews por PR), sin un servidor Node en producción |
| Auth | **Supabase Auth, proveedor Google únicamente** (el proveedor Email queda deshabilitado) | Un clic para registrarse y entrar: los docentes ya tienen cuenta de Google. Sin contraseñas que guardar, resetear o filtrar, y el email llega verificado por Google. La API solo verifica JWTs. Configuración en §5.2c |
| Backend API | FastAPI + Pydantic v2 + SQLAlchemy 2 async (asyncpg) + PyJWT (verificación con JWKS) | **El motor de PDF elegido (WeasyPrint) es Python**, igual que el mejor tooling para validar la salida del LLM (Pydantic). Un solo lenguaje en servidor. FastAPI genera OpenAPI, de donde salen los tipos del frontend (`openapi-typescript`) |
| Worker | Proceso Python asyncio (misma imagen y mismo código que la API, otro comando: `python -m app.worker`) | Comparte modelos, prompts y validación con la API. asyncio permite 16 llamadas lentas en vuelo en un solo proceso |
| Cola | Tabla `generation_jobs` en Supabase Postgres con `FOR UPDATE SKIP LOCKED` | Ver §7, D4 |
| Base de datos | **Supabase Postgres** (plan Pro en producción) | `jsonb` para `content_json`, transacciones que cubren dato + job, cola integrada. Backups diarios y pooler incluidos |
| Tiempo real | **Supabase Realtime** (`postgres_changes` sobre `generation_jobs`) | El progreso aparece al instante sin websockets propios |
| Almacenamiento de PDFs | **Supabase Storage**, bucket privado `exports` + URLs firmadas | Los PDFs no se guardan en la DB, y es un proveedor menos que con R2. El worker sube con el SDK `supabase-py` (service role) |
| Despliegue | Supabase (gestionado) + **Vercel** (frontend) + **Render** (API como *Web Service*, worker como *Background Worker*) | Vercel sirve los estáticos y reenvía `/api/*` a `api.<dominio>` en Render (§5.2d). Render construye la imagen Docker desde GitHub, da TLS y despliega sin servidor que administrar (§5.2e). Los servicios no tienen estado: la base, los archivos y las cuentas viven en Supabase. Ver §7, D9 |
| Desarrollo local | `supabase start` (Supabase CLI en Docker: Postgres, Auth, Storage y Realtime locales) + `docker compose up api worker` (misma imagen que en Render) | Mismo stack en local y en producción; las migraciones se prueban con `supabase db reset` |
| Observabilidad | Logs JSON estructurados (con `job_id` y `series_id` en cada línea), Sentry (API + worker + frontend), métricas desde `generation_logs` | `generation_logs` *es* el dashboard de coste y latencia: es SQL, no hace falta otro sistema |

### 5.2 Integración con DeepSeek: **API directa**, no MCP

- **Cliente:** el SDK oficial `openai` de Python con `base_url="https://api.deepseek.com"`. La API de DeepSeek es compatible con la de OpenAI, así que no hace falta un SDK propio ni HTTP a mano, y cambiar de proveedor sería cambiar `base_url` y `model`.
- **Modelo:** `deepseek-chat` (modo sin razonamiento) para esquema y lecciones. El modo razonador añade latencia y tokens de "pensamiento" que no mejoran prosa didáctica estructurada. El modelo se define en config (`DEEPSEEK_MODEL_OUTLINE`, `DEEPSEEK_MODEL_LESSON`) para poder probar el razonador solo en el esquema sin tocar código.
- **Salida estructurada:** `response_format={"type": "json_object"}`. DeepSeek exige que el prompt mencione "json" e incluya un ejemplo del formato; el system prompt lleva el JSON Schema y un ejemplo mínimo. JSON mode garantiza JSON sintácticamente válido pero **no** que cumpla el schema, de ahí la validación Pydantic + reparación (§2.2).
- **Tamaño por llamada:** el diseño asume **≤ 8k tokens de salida por llamada** (el límite de `deepseek-chat` cuando se escribió este documento; **verificar el límite vigente al implementar**). Una lección de 50 min con 6–10 ejercicios cabe en 3–6k tokens. Por eso **el bloque de generación es la lección** y no la serie: generar 10 lecciones en una sola llamada truncaría y convertiría un fallo en 10.
- **Streaming en el worker** (no hacia el usuario): solo para los timeouts de inactividad (§2.2) y para medir `time_to_first_token_ms`.
- **Parámetros:** `temperature` 1.0 en lecciones y 0.7 en el esquema (más estable); `max_tokens` explícito siempre.
- **Rate limiter:** `aiolimiter.AsyncLimiter(DEEPSEEK_RPM, 60)` + `asyncio.Semaphore(DEEPSEEK_MAX_INFLIGHT)` en el proceso worker. Como solo hay **un** proceso worker, el limitador en memoria es global de verdad.
- **Por qué no MCP:** MCP sirve para exponer herramientas y datos *a un agente LLM* que decide cuándo usarlas (p. ej. Claude Desktop llamando a tus herramientas). Aquí no hay agente: nuestro backend es el orquestador y sabe exactamente qué llamada hacer y cuándo. Meter MCP añadiría un proceso, un protocolo y un salto de red entre el worker y DeepSeek sin aportar nada. Además, DeepSeek se consume como API HTTP, no como servidor MCP. *Reconsiderar* solo si en el futuro se quiere que un asistente externo opere la app ("créame una serie sobre X"); en ese caso sería un servidor MCP **delante de nuestra API**, no entre el worker y DeepSeek.

### 5.2b Conexión a Supabase Postgres

- API y worker son **procesos persistentes**, así que conectan a través de **Supavisor en *session mode*** (host del pooler, puerto 5432). Se descarta:
  - *Transaction mode* (puerto 6543): no admite los prepared statements que usa asyncpg, y el `SELECT … FOR UPDATE SKIP LOCKED` + `UPDATE` del worker necesita una transacción en la misma conexión.
  - La conexión directa a la base: solo tiene IPv6, salvo que se contrate el add-on de IPv4.
- Pools pequeños y fijos: API `pool_size=10`, worker `pool_size=5`. El worker no retiene la conexión mientras espera a DeepSeek: **toma el job y hace commit, llama a DeepSeek sin conexión abierta, y luego abre otra transacción para guardar el resultado.** Si no, 16 llamadas en vuelo de 90 s retendrían 16 conexiones.
- Variables: `DATABASE_URL` (pooler, session mode), `SUPABASE_URL` (de ella se derivan el issuer `…/auth/v1` y el JWKS `…/auth/v1/.well-known/jwks.json`), `SUPABASE_SERVICE_ROLE_KEY` (solo worker y API: Storage). En el frontend (variables de Vercel) solo `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY`, que son públicas por diseño y están protegidas por RLS. En proyectos con las API keys nuevas de Supabase, `VITE_SUPABASE_ANON_KEY` lleva la *publishable key* (`sb_publishable_…`) y `SUPABASE_SERVICE_ROLE_KEY` la *secret key* (`sb_secret_…`).

### 5.2c Login con Google: configuración

**Google Cloud Console** (un proyecto propio de la app):

- Pantalla de consentimiento OAuth: tipo **External** (para aceptar cualquier cuenta de Google, también de Workspace de otros centros), nombre de la app, logo, dominio, política de privacidad y términos. Se envía a **verificación de marca** antes del lanzamiento, para que los admins de Workspace la vean como app verificada.
- Scopes: solo `openid`, `email` y `profile`. Son no sensibles, así que no requieren la verificación larga de Google. **No** se piden Drive ni Gmail: la app no los necesita y pedirlos espantaría a los docentes.
- Cliente OAuth tipo *Web application*:
  - *Authorized redirect URI*: `https://<ref>.supabase.co/auth/v1/callback` y, para desarrollo, `http://127.0.0.1:54321/auth/v1/callback`.
  - *Authorized JavaScript origins*: el dominio de la app y `http://localhost:5173`.

**Supabase** (dashboard → Authentication):

- Providers → Google: activado con el *client ID* y el *secret* de Google. Providers → **Email: desactivado**, así no hay un camino de registro alternativo.
- URL Configuration: *Site URL* = dominio de producción. *Redirect URLs* permitidas = `https://<dominio>/auth/callback`, la URL de staging y `http://localhost:5173/auth/callback`.
- En local, `supabase/config.toml` → `[auth.external.google] enabled = true`, con `client_id` y `secret` desde `env(...)`; nunca commiteados.

**Frontend:**

- `createClient(url, anonKey, { auth: { flowType: 'pkce', detectSessionInUrl: true, persistSession: true } })`.
- Botón: `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${origin}/auth/callback` } })`.
- Ruta `/auth/callback`: espera a que `supabase-js` intercambie el `code` y redirige a la página que el usuario intentaba abrir (guardada antes de iniciar el login).
- Rutas protegidas: sin sesión → `/` ("Continuar con Google").

**Decisiones menores:**

- Se acepta cualquier dominio de Google. Si en el futuro un centro quisiera restringirlo, el hook *before user created* de Supabase Auth permite filtrar por dominio sin tocar la API.
- La pantalla de consentimiento muestra "continuar a `<ref>.supabase.co`" salvo que se configure un **dominio personalizado en Supabase** (add-on de pago). Se recomienda activarlo antes del lanzamiento público, porque un dominio desconocido en el consentimiento reduce la confianza.

### 5.2d Despliegue en Vercel (frontend)

- Proyecto de Vercel con *Root Directory* `frontend/`, framework Vite, comando `npm run build`, salida `dist/`.
- `frontend/vercel.json`: el rewrite a la API va **antes** del fallback de la SPA. Vercel no interpola variables en `vercel.json`, así que la URL de la API está escrita en el archivo.

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://api.<dominio>/api/:path*" },
    { "source": "/((?!assets/).*)", "destination": "/index.html" }
  ]
}
```

- **Variables de entorno en Vercel**: solo las públicas del frontend (`VITE_*`, §5.2b). Vite las incrusta en el bundle **en el build**, así que un cambio exige redeploy. Ningún secreto va a Vercel.
- **Previews:** cada PR tiene una URL `*.vercel.app`. Para que el login con Google funcione en ellas, en Supabase → Redirect URLs se añade el patrón `https://*-<equipo>.vercel.app/**`. Las previews apuntan al proyecto de Supabase de **staging**, no al de producción: las variables se definen por entorno (*Preview* / *Production*).
- **No usar la integración Vercel ↔ Supabase del marketplace.** Crea variables con nombres de Next.js (`NEXT_PUBLIC_*`, que Vite no expone) y copia al proyecto de Vercel secretos como `SUPABASE_SERVICE_ROLE_KEY` y `POSTGRES_URL`, que aquí no deben estar.

### 5.2e Despliegue en Render (API + worker)

Dos servicios construidos desde **la misma imagen** (`backend/Dockerfile`, con WeasyPrint, Pango y las fuentes instaladas), definidos como código en `render.yaml` (*Blueprint*):

```yaml
envVarGroups:
  - name: generador-backend
    envVars:
      - key: DATABASE_URL            # pooler Supabase, session mode
        sync: false                  # sync: false = el valor se introduce en el dashboard, nunca en el repo
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: DEEPSEEK_API_KEY
        sync: false
      - key: DEEPSEEK_RPM
        value: "50"
      - key: DEEPSEEK_MAX_INFLIGHT
        value: "16"

services:
  - type: web
    name: generador-api
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    region: oregon                 # la misma región que el proyecto de Supabase (us-west-2)
    plan: starter
    healthCheckPath: /api/health
    autoDeployTrigger: checksPass  # despliega solo si pasan los checks de GitHub (incluida la migración)
    envVars:
      - fromGroup: generador-backend

  - type: worker
    name: generador-worker
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    dockerCommand: python -m app.worker
    region: oregon
    plan: standard                 # más RAM: WeasyPrint + 16 llamadas en vuelo
    numInstances: 1                # OBLIGATORIO: el rate limiter de DeepSeek vive en memoria
    autoDeployTrigger: checksPass
    envVars:
      - fromGroup: generador-backend
```

Reglas de operación:

- **API:** el `CMD` del Dockerfile escucha en `$PORT` (lo define Render). `GET /api/health` responde `200` si la DB contesta; Render solo da tráfico a la nueva versión cuando el health check pasa, así que los deploys de la API no tienen downtime.
- **Dominio:** *custom domain* `api.<dominio>` en el servicio `generador-api`. Render emite el certificado TLS, y es el destino del rewrite de Vercel (§5.2d).
- **El worker nunca escala a más de 1 instancia** mientras el rate limiter esté en memoria (§6, "varios workers").
- **Apagado limpio del worker:** al desplegar, Render envía `SIGTERM`. El worker deja de tomar jobs nuevos y espera a los que están en vuelo hasta el período de gracia configurado (`maxShutdownDelaySeconds`, subirlo al máximo permitido). Si un job no termina a tiempo, el *lease* de 10 min lo devuelve a la cola (§2.2), sin perderlo ni duplicarlo.
- **Plan:** sin plan gratuito en producción. Los *Web Services* gratuitos se duermen tras inactividad (el primer request tarda decenas de segundos) y los *Background Workers* no tienen plan gratuito. Ajustar los planes según la RAM observada en las métricas de Render.
- **Migraciones antes del deploy:** un GitHub Action en cada push a `main` ejecuta `supabase db push` contra producción. Con `autoDeployTrigger: checksPass`, Render despliega **solo si ese check pasa**, así que nunca corre código nuevo sobre un esquema viejo. Las migraciones deben ser compatibles hacia atrás (añadir antes de quitar), porque durante el deploy conviven brevemente la versión vieja y la nueva.
- **Logs:** Render guarda stdout de ambos servicios. Los logs JSON (§5.1) se filtran por `job_id`. Sentry sigue siendo el canal de errores.

> Verificar al implementar: los nombres exactos de campo del Blueprint (`autoDeployTrigger`, `maxShutdownDelaySeconds`) y los planes vigentes en la documentación de Render.

### 5.3 Generación de PDF: **WeasyPrint**, no ReportLab

Pipeline: `content_json` → plantilla **Jinja2** (`templates/pdf/classic/*.html.j2` + `classic.css`) → HTML → **WeasyPrint** → PDF.

- **Por qué WeasyPrint:** el entregable es un documento editorial (portada, índice con números de página, cabeceras y pies con el título de la lección, numeración, saltos de página controlados, cajas de "Idea clave", líneas para responder, solucionario). Todo eso es **CSS Paged Media**: `@page` con márgenes con nombre, `string-set` para cabeceras corridas, `target-counter()` para el índice, `break-before: page`, `break-inside: avoid` en ejercicios y tablas. La maquetación vive en HTML/CSS, que cualquier diseñador o desarrollador web puede editar e iterar renderizando en local, y se puede añadir una segunda plantilla sin tocar Python.
- **Por qué no ReportLab:** su API es imperativa (posicionar *flowables* desde código Python). Cada cambio de diseño es un cambio de código, la paginación compleja (índice con números de página reales, cabeceras que cambian por lección) hay que programarla a mano, y la plantilla no se puede previsualizar ni iterar como CSS. Es más rápido renderizando, pero aquí el render (5–30 s en un job asíncrono) no es el cuello de botella; la calidad y el coste de iterar el diseño sí.
- **Por qué no un Chromium headless (Puppeteer/Playwright):** soporta peor CSS Paged Media (cabeceras corridas, `target-counter`), necesita ~300 MB de navegador en la imagen y es más frágil de operar. WeasyPrint no ejecuta JS, lo cual aquí es una ventaja: superficie de ataque mínima.
- **Limitaciones aceptadas de WeasyPrint:** no ejecuta JavaScript, y su soporte de CSS Grid y Flexbox es más limitado que el de un navegador. Las plantillas usan flujo de bloques, tablas y floats, que es lo que necesita un documento impreso.
- **Fuentes:** embebidas en la imagen Docker (p. ej. Source Serif 4 para el cuerpo y Inter para los títulos, ambas con licencia OFL), con cobertura de acentos y ñ.
- **Seguridad:** autoescape de Jinja2 activado; `url_fetcher` personalizado que solo permite `file://` dentro de `templates/pdf/assets/`.
- **Determinismo:** el mismo contenido y las mismas opciones producen el mismo PDF, y eso habilita la caché por `content_hash` (§3.8).

### 5.4 Estructura del repositorio

```
generador/
├─ ARCHITECTURE.md
├─ docker-compose.yml          # solo desarrollo local: api + worker contra `supabase start`
├─ render.yaml                 # Blueprint de Render: api (web), worker, env group
├─ supabase/                   # Supabase CLI
│  ├─ config.toml
│  ├─ migrations/              # tablas, enums, RLS, trigger de profiles, publicación Realtime, bucket `exports`
│  └─ seed.sql                 # usuario y serie de ejemplo para desarrollo local
├─ frontend/                   # Vite + React + TS
│  ├─ vercel.json              # rewrites /api/* y fallback SPA (Root Directory de Vercel = frontend/)
│  └─ src/{routes,components,api,lib/supabase.ts}/
└─ backend/
   ├─ app/
   │  ├─ api/                  # routers FastAPI (me, series, lessons, exports) + deps.py (verificación JWT)
   │  ├─ domain/               # modelos Pydantic: content_json, estados, transiciones
   │  ├─ db/                   # modelos SQLAlchemy, sesión
   │  ├─ jobs/                 # queue.py (claim/lease/reaper), handlers por kind
   │  ├─ llm/                  # deepseek_client.py, rate_limiter.py, prompts/{outline,lesson,block}@vN.md
   │  ├─ pdf/                  # render.py, templates/classic/, assets/fonts/
   │  ├─ storage.py            # subida y URLs firmadas (supabase-py)
   │  └─ worker.py             # entrypoint del worker
   └─ tests/
      └─ fixtures/deepseek/    # respuestas grabadas (válidas, inválidas, truncadas)
```

### 5.5 Estrategia de pruebas

- **Cliente DeepSeek simulado** con respuestas grabadas: válidas, JSON roto, truncadas (`finish_reason=length`), `429`, `503`, timeout. Los tests de reintentos y estados no tocan la red.
- **Tests de contrato:** cada fixture válida pasa el schema de `content_json`; cada endpoint coincide con el OpenAPI.
- **Tests de máquina de estados:** transiciones válidas e inválidas de Series y Lesson.
- **Tests de RLS** contra el Supabase local (`supabase start`): con el JWT de un usuario A, intentar `SELECT` sobre series, lecciones, jobs y exports de B → 0 filas; `INSERT/UPDATE` desde `authenticated` → denegado; `generation_logs` → 0 filas siempre. Se ejecutan en CI tras `supabase db reset`.
- **Test de verificación JWT** en la API: token caducado, `aud` incorrecto, firma de otro proyecto → `401`.
- **Login en tests automáticos:** el OAuth real de Google no se automatiza en CI. Los tests de API y RLS crean usuarios con la Admin API del Supabase local (`auth.admin.createUser`) y firman sesiones de prueba. Un único test E2E manual o semiautomático en staging verifica el flujo real de Google (consentimiento → callback → sesión → creación de `profiles`).
- **Smoke test de PDF en CI:** se renderiza una serie fija, se verifica el número de páginas, que el texto extraído contenga títulos y respuestas en el solucionario (y **no** en el cuerpo), y que las fuentes estén embebidas.
- **Eval de prompts** (manual, por versión de prompt): 5 temas × 3 niveles; se revisan la tasa de validación al primer intento y una rúbrica de calidad. El cambio de `prompt_version` queda registrado en `generation_logs`.

---

## 6. Fuera de alcance en v1 (y cómo encajaría después)

| Fuera de v1 | Por qué | Cómo encajaría |
|---|---|---|
| Fórmulas matemáticas | WeasyPrint no ejecuta KaTeX/MathJax; el soporte de MathML es parcial | Nuevo tipo de bloque `math` con LaTeX, renderizado a SVG en el servidor al guardar (KaTeX vía un microservicio Node o `latex2svg`) |
| Imágenes / ilustraciones | Coste, derechos y calidad variable | Bloque `image` con `storage_key`; subida manual del docente primero, generación después |
| Ver el texto aparecer en vivo (streaming a la UI) | Realtime ya cubre el progreso por lección; emitir tokens sueltos multiplica los eventos | El worker publica fragmentos por **Realtime Broadcast** en el canal `series:{id}` (efímeros, sin escribir en la DB) |
| Colaboración entre docentes | — | `series_members` + permisos |
| Varios workers / alta escala | Un worker con 16 llamadas en vuelo da ~600 lecciones/h | Mover el rate limiter a Redis (o advisory locks de Postgres) y lanzar N workers |
| Exportar a DOCX | — | Segundo renderer desde el mismo `content_json` (`python-docx`) |

---

## 7. Registro de decisiones

| # | Decisión | Elegido | Descartado | Razón |
|---|---|---|---|---|
| D1 | Arquitectura de aplicación | React SPA + FastAPI | Next.js full-stack | El motor de PDF y la validación del LLM son Python. Con Next.js habría igualmente un servicio Python para el PDF, y los route handlers no sirven para jobs de varios minutos (timeouts de serverless). No hay SEO que justifique SSR |
| D2 | Integración LLM | API directa vía SDK `openai` | MCP | No hay agente que elija herramientas; MCP añade un proceso y un salto sin beneficio (§5.2) |
| D3 | Motor PDF | WeasyPrint | ReportLab, Chromium headless | Paged Media en CSS, plantillas editables sin tocar Python; ReportLab es imperativo y Chromium pesado y peor en paginación (§5.3) |
| D4 | Cola de trabajos | Tabla propia en Supabase Postgres con `SKIP LOCKED` | Celery/RQ/Arq + Redis; Supabase Queues (pgmq) | Un servicio menos que operar; encolar va en la **misma transacción** que el cambio de estado (no hay jobs huérfanos ni series sin job). La tabla de jobs es a la vez la cola, el estado para la UI, la fuente de Realtime y la base de idempotencia y cuotas. Con pgmq habría que mantener mensajes y estado en dos sitios. Al volumen de v1 (cientos de jobs/h), Postgres sobra |
| D5 | Unidad de generación | 1 llamada = 1 lección (+ 1 para el esquema) | Toda la serie en una llamada; lección a lección secuencial con contexto acumulado | En una sola llamada la serie excede el límite de salida y un fallo lo pierde todo. El modo secuencial es 10 veces más lento. Usar el esquema como contrato permite paralelizar manteniendo la coherencia |
| D6 | Formato del contenido | JSON por bloques con schema | Markdown libre; HTML del LLM | Un mismo formato sirve al editor por bloques, a la regeneración de un bloque concreto, al solucionario separado y a la plantilla PDF. Además es validable y seguro (sin HTML del modelo) |
| D7 | Progreso en la UI | Supabase Realtime (`postgres_changes` en `generation_jobs`) como **señal** + refetch de `/progress` | Polling cada 2 s; SSE propio; Realtime con el contenido completo en el evento | Con Supabase, el tiempo real no cuesta infraestructura propia. Usarlo solo como señal mantiene una única fuente de verdad (la API) y hace inofensivos los eventos perdidos (refetch al reconectar + polling de seguridad de 15 s) |
| D8 | Auth | **Supabase Auth con Google OAuth como único método** (registro = primer login); la API verifica el JWT con JWKS | Email + contraseña (además o en lugar de Google); magic link; auth propio; Clerk/Auth0 | Los docentes ya tienen cuenta de Google, personal o del centro: registro y login en un clic, sin contraseñas que resetear ni emails de confirmación que se pierden en spam. Un solo método evita cuentas duplicadas (mismo email con contraseña y con Google). Coste aceptado: quien no tenga Google no puede entrar, y algunos centros bloquean apps externas (mitigado en §2.2). Verificar con JWKS es local (sin una llamada a Supabase por request). Coste aceptado: el token vive en `localStorage` (riesgo XSS), mitigado con CSP estricta y con que el LLM nunca produce HTML |
| D9 | Hosting | Supabase gestionado + **Vercel solo para el frontend** + **Render** para API y worker | Todo en Supabase (Edge Functions); API y worker como Vercel Functions; VPS propio con Docker Compose; Railway | Vercel es ideal para la SPA (CDN, previews por PR). Pero los jobs duran minutos, el worker es un proceso permanente y WeasyPrint necesita librerías del sistema (Pango): nada de eso cabe en funciones serverless. Render ejecuta contenedores Docker siempre encendidos y tiene un tipo de servicio específico para workers. Frente a un VPS ahorra administrar la máquina (parches, TLS, despliegues), a cambio de algo más de coste. Frente a Railway (equivalente), se eligió Render por preferencia del equipo |
| D13 | Alcance de Supabase | Auth, Postgres, Storage, Realtime | Edge Functions para generación o PDF; frontend leyendo y escribiendo tablas con `supabase-js` | Edge Functions: runtime Deno (sin WeasyPrint ni Pydantic) y límites de tiempo por invocación, incompatibles con llamadas de 1–2 min y reintentos con backoff. El acceso directo a tablas desde el navegador repartiría la máquina de estados, las cuotas y el encolado entre políticas RLS y la API; con todas las escrituras en la API, las reglas viven en un único sitio y se testean en Python |
| D14 | Conexión a la DB | Supavisor *session mode* | *Transaction mode*; conexión directa | Ver §5.2b: asyncpg + transacciones del worker; la conexión directa es solo IPv6 |
| D15 | Migraciones | Supabase CLI (SQL) | Alembic | RLS, publicación de Realtime, buckets y el trigger sobre `auth.users` son SQL específico de Supabase que Alembic no modela. Una sola fuente de esquema; SQLAlchemy mapea tablas sin autogenerar migraciones |
| D10 | Modelo DeepSeek | `deepseek-chat` (sin razonamiento) | `deepseek-reasoner` | Menor latencia y coste para prosa estructurada; configurable si una eval demuestra lo contrario para el esquema |
| D11 | Regenerar sobre contenido editado | Propuesta (`pending_content_json`) + diff | Sobrescribir | El trabajo manual del docente nunca se pierde en silencio |
| D12 | Límite de lecciones por serie | 20 | Ilimitado | Acota el tiempo de render del PDF, el coste por serie y el abuso. Un curso más largo se divide en varias series |
