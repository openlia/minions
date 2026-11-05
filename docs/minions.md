# Documents, skills, and Minions

Minions are programmable workspace apps, not a replacement for every template.

| Building block | Responsibility |
| --- | --- |
| Profile | Select features, skills, and starter instructions |
| Feature | Bundle domain records, schemas, skills, dependencies, and eventually optional Minions |
| Skill | Teach Hermes how to perform a workflow |
| Inline OpenUI | Present information inside an ordinary Markdown document |
| Minion | Provide an executable app with input, configuration, dashboard, and tests |

## Choose the smallest useful building block

Keep tasks, goals, contacts, research, decisions, claims, and clinical history as
durable records. Add inline views when they help. Use a Minion for an interactive
tracker or app with meaningful input handling or enrichment, such as a gym
tracker, family menu, portfolio watch, or condition monitor.

Use the runtime's protected `minion-authoring` skill and `minion_scaffold`,
`minion_validate`, and `minion_run` tools. Apps live in `minions/<slug>/` and link
through `openlia://minions/<slug>`. Document views link through
`openlia://workspace/<path>`; skills use `openlia://skills/<id>`.

Keep one authoritative location per dataset. An optional task app should read
the existing `tasks/` records rather than silently copy them into a second store.
Minions may own canonical app data. Personal Finance and Personal Health keep
their durable Markdown records and journals under `minions/<app>/data/`, shared
with their skills, not duplicated in a second store. Ingestion originals remain
in the Vault. Portable templates/schemas stay outside instance data, in `templates/`.

## Workflow discovery

Collection discovery identifies each Minion once, not its scripts, tests,
dependency packages, schemas, or nested data folders as separate collections.
Minions declare named structured views in reviewed `data.views.json` files.
OpenLia's runtime validates and reads these through approved `markdown`, `json`,
or `calendar` adapters; Calendar reuses the same native service as its dashboard.
Hermes uses `minion_describe` and `minion_query`; daily briefing calls the bundled
runtime CLI, not app entrypoints or its own data scanner. A missing reader or
invalid source is unavailable, never an empty calendar or zero activity.

Installing a declaration does not enable scheduled disclosure. Local `config.json`
opts into view IDs under `data_views.briefing` (default `[]`). Optional
`data_views.scopes` constrains every query, and callers cannot widen that scope.
Health review views require an explicit `person_id`; it is never inferred.
Only declared scalar fields are returned, never Markdown bodies, code, tests,
dependencies, pending state, or caches. Date windows, scan budgets, field lengths,
and result limits are enforced by the runtime; truncation is reported. Ordinary
workspace sources are not removed merely because a Minion has similar data.
Dashboard visibility/pagination is not permission. Link canonical records and
avoid counting duplicate representations of the same record.
Missing exports do not mean zero activity. Reading a report must never run code.

## Migrating old Mini-Projects

The former `project-manifest.toml` + `ui.openui` model and
`openlia://projects/...` links are no longer the authoring contract. New catalog
packages do not ship those artifacts. Existing domain templates and records
remain in place; they do not need to become Minions.

For an existing installation:

1. Inspect local records, old views, and customizations before updating.
2. Use the normal feature/profile update and managed rebase workflow. Syncing the
   catalog alone does not migrate installed content.
3. Replace useful document presentations with fenced `openui` blocks in Markdown.
   Honor the containing folder's template and schema. Discover current APIs with
   `openui_describe`; validate with `openui_validate` and preview rendering.
4. If executable app behavior is needed, scaffold a separate Minion and connect
   it to the existing records. Do not merely rename the old UI file.
5. Update links and instructions after reviewing the replacement. Never delete
   user-customized legacy files or records simply because the catalog dropped
   its old scaffold.

Legacy `DomainHeader`, `RecordKanban`, `RecordTable`, and `@Query` expressions
are not supported live bindings in the current renderer. Literal OpenUI tables
are snapshots, not automatically refreshed collection queries. Do not substitute
fabricated counts or an empty table presented as live data.

## Code-only distribution through features

The paired runtime introduces `minion.package.json`, an explicit reviewed source
file list. Declare each app as an exact `minions/<slug>` feature domain and place
its distributable tree under `workspace/minions/<slug>/`. Do not select the whole
`minions` namespace or a state subdirectory. A typical manifest is:

```json
{
  "schema": 1,
  "files": [
    "README.md", "dashboard.openui", "input.openui",
    "input.schema.json", "config.schema.json",
    "input.py", "main.py", "requirements.txt", "tests/test_main.py"
  ]
}
```

An app may also list reviewed `data.views.json`. Its sources stay under the app's
`data/` directory; no declaration may supply executable reader code. For example:

```json
{"schema":1,"views":[{"id":"sessions","label":"Workout sessions","reader":"json","path":"data/items.json","fields":["item","date","status"],"title_field":"item","date_field":"date","max_records":20}]}
```

To opt in locally, save `"data_views": {"briefing": ["sessions"], "scopes": {}}`
in Configuration. A Health scope would instead include
`"scopes": {"follow-ups": {"person_id": "person-001"}}`. Do not populate private
recipient scopes in distributed defaults. Test exact runtime/catalog revisions
together before promoting this development contract.

The manifest is included implicitly. Use individual relative files, not globs.
Include both schemas/views, one runtime and its input handler, and tests. List
helpers, dependencies, and reviewed `tests/fixtures/` inputs explicitly.

Both exporters exclude local `config.json`, `data/`, state, caches, environments,
installed dependencies, logs, uploads, hidden paths, and credential-like files,
even with `include_records`. Clean catalog/import packages must contain only
declared portable files; use feature export to package a live app first. Review
every declared file and the archive: generated dashboards, code, tests, and
schema defaults can still contain personal data that a credential scan cannot
recognize. A file list is not a privacy guarantee or code sandbox.

Fresh installation derives configuration from schema defaults, with automatic
triggers off and no cron schedule. Missing user settings leave configuration
pending; entry/main/heartbeat execution requires valid local config. Installation
does not run app code, tests, or app dependency hooks. Browser installation
refuses existing apps; managed CLI update/reimport uses code-only 3-way rebase,
preserving settings, records, and intentional local deletions. Feature removal
keeps the app directory; it does not disable manual execution.

See the paired runtime's [full distribution contract](https://github.com/openlia/openlia/blob/main/docs/minion-distribution.md)
for supported defaults, collision handling, archive layouts, and update behavior.
Before the first stable release, coordinated development previews intentionally
leave `requires.openlia` unset and test exact runtime/catalog commit SHAs together.
An unset minimum provides no minimum-version guard or compatibility guarantee.
For stable catalog releases, declare the actual first compatible **released**
runtime requirement. Do not invent a minimum, move a published version tag, or
promote an untested catalog pin merely to preview an app.

Automatic scheduling, enable/disable behavior, timezone handling, concurrency,
retries, and scheduling permissions remain the next phase. A cron value alone is
not a registered schedule. Pilot with a gym tracker and condition monitor after
those contracts are tested; keep external effects approval-gated.
