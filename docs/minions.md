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
Minions are excluded from generic briefing sources. To include a result in a
briefing or review, publish an intentional, dated Markdown report outside
`minions/`, following that destination's local template and permissions. Link
the source Minion and canonical records; do not also count the app's cached copy.
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
This is a new runtime capability: before publishing a catalog app, assign its
actual first compatible **released** runtime requirement and test the exact pair.
Do not invent a release minimum or promote an untested catalog pin.

Automatic scheduling, enable/disable behavior, timezone handling, concurrency,
retries, and scheduling permissions remain the next phase. A cron value alone is
not a registered schedule. Pilot with a gym tracker and condition monitor after
those contracts are tested; keep external effects approval-gated.
