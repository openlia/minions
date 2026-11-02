# Contributing to `openlia/minions`

The runtime in `openlia/openlia` supplies reusable capabilities. This repository
assembles them into profiles, features, Minions, document views, and skills. Keep those
responsibilities separate, but deliver dependent changes together.

## Documents, skills, and Minions

Profiles select a starter experience. Features bundle domain records, schemas,
skills, and dependencies. Skills teach Hermes workflows. Inline OpenUI presents
information in Markdown; Minions add executable input, configuration, and
dashboard behavior. Do not convert a document collection into an app merely to
provide a view. See [the Minions guide](docs/minions.md) for migration boundaries
and the runtime work required before publishing catalog Minions.

The catalog registry helper in `scripts/workspace_registry.py` is also distributed
inside workflow skills so they work independently after installation. Keep those
copies identical; the unit suite checks every copy against the canonical helper.

## Runtime compatibility

When content needs a runtime capability that older releases lack, declare its
minimum **released** OpenLia version in `feature.yaml`, `profile.yaml`, or the
YAML frontmatter of `SKILL.md`:

```yaml
requires:
  openlia: ">=1.2.3" # Example only; choose the actual first compatible release.
```

The initial contract supports only `>=MAJOR.MINOR.PATCH`, with no leading zeros.
Ranges, prerelease minima, tags, commit SHAs, and PR numbers are not supported.
Do not add a requirement unless you can identify the compatible release.

- Missing `requires.openlia` preserves legacy behavior; it does not prove that
  the content works on every runtime.
- Features inherit runtime requirements from required features and bundled
  skills. Profiles inherit requirements from every selected feature and skill.
- A directly installed feature-bundled skill also inherits its owning feature's
  requirements. Standalone skills must declare their own requirements.
- The enforcing runtime checks the deployed Workspace UI image's baked release
  identity, not the caller's CLI version or a version environment override.
- Both CLI operations and the browser feature-install API enforce the guard.
- The browser refuses replacement of any active/disabled skill before writing
  dependencies. Use the managed CLI for updates, customized/forked skills, and
  re-enablement; browser installation is limited to new skill destinations.
- Incompatible or unverifiable targets are rejected before installed workspace
  files, skills, or provenance are changed. Whole profiles are preflighted before
  their first feature is installed. This is a compatibility check, not a general
  transaction/rollback guarantee for later I/O failures.
- Older runtimes may ignore this field. Publish the enforcing runtime before
  relying on it; do not assume new metadata protects old clients consuming `main`.

## Paired runtime/template changes

Use one parent issue and one delivery owner. In both PRs include:

- The parent issue and companion PR.
- The new runtime capability and its first compatible release.
- Exact runtime/template commit SHAs used for the combined test.
- Results for a compatible pair and rejection by the enforcing runtime against
  an older deployment; local evidence is not production acceptance.
- Rollout order: deploy the compatible runtime, then install/update the template,
  then verify the end-to-end experience on the target deployment.
- Recovery: preserve user files and use the normal feature/skill rebase flow;
  do not overwrite customized workspaces to make a test pass.

For Calendar 0.2.0, the companion runtime is `openlia/openlia#186`. Its release
number has not been encoded here. Before publishing content that relies on the
new guard, assign and deploy the compatible runtime release and add that actual
minimum to `features/calendar/feature.yaml`. Do not use the unchanged development
version as evidence that an older image has the Calendar components.

## Local development

Use sibling checkouts, with feature branches in both repositories:

```text
dev/
├── open_lia/
└── openlia_minions/
```

In the **disposable local deployment's** OpenLia `config.toml`, explicitly select
the catalog checkout:

```toml
[templates]
repo = "/absolute/path/to/dev/openlia_minions"
```

Run `openlia features sync` against that deployment to refresh its catalog cache.
The deployed UI reads the synced cache, not necessarily live checkout edits.
After editing templates, sync again and use the normal install/update/rebase
flow. Sync alone does not update existing installed files. Runtime/image changes
require rebuilding and deploying Workspace UI. A path on your laptop is not a
valid catalog path on a remote SSH host.

Local development is explicit: leave `templates.ref` unset to read the live
checkout. A local Git path with a ref selects a detached snapshot. Unconfigured
sibling directories no longer override production catalog selection.

When sync replaces a changed cache, it reports `ui_refresh_required` and retains
the old `previous_cache_dir` for running Docker bind mounts. Recreate Workspace
UI with the target's Compose configuration (`up -d --no-deps --force-recreate
workspace-ui`); a plain restart does not replace the mount. Remove retained
snapshots individually only when no containers use them and they are no longer
 needed for recovery. Identical-content syncs preserve any outstanding refresh
requirement until the running UI's generation is verified. Activation journals
allow interrupted syncs to recover locally without a fresh fetch.

After all consumers have released old mounts, operators can deliberately run
`openlia features cache-prune --keep 2 --confirm-unmounted` to bound identified
retired snapshots. Unknown/modified directories and the active cache are never
pruned. No background cleanup guesses whether another container still uses one.

## Test both repositories in one pass

From the runtime checkout, install its integration prerequisites and run:

```sh
python3 -m pip install -r requirements-templates-integration.txt
bun install --frozen-lockfile --ignore-scripts
bun run --cwd packages/workspace-ui browser:install
make templates-integration TEMPLATES_ROOT=../openlia_minions
```

Native Remind must be available; the underlying Python runner also accepts
`--remind-binary /path/to/remind`. Everything is tested in temporary workspaces,
including uncommitted template edits. Both HEADs, dirty state, content digests,
feature versions, diagnostics, and native Calendar desktop/mobile acceptance are
recorded. `--skip-browser` is contract-only, not UI acceptance evidence.

The runner tests the actual catalog through **both** Go and TypeScript installers,
including Go profiles, skills, packaging, and archive import. Add `--docker` to
the Python command (or `TEMPLATES_INTEGRATION_ARGS=--docker` to Make) to verify
mount refresh behavior in a disposable Compose project. It does not deploy a
Workspace UI image or touch an existing deployment.

For two PRs, dispatch **Runtime and templates integration** in `openlia/openlia`
with their `runtime_ref` and `templates_ref` (branches, tags, SHAs, or
`refs/pull/N/head`). Link that single run from both PRs. The workflow uses
read-only permissions, no deployment secrets, and never publishes changes.

## Validation

Manifests/profiles/skill requirements support block and flow YAML consistently.
`requires.python` and `requires.bun` name relative environment-manifest files
(for example `requirements.txt` and `package.json`), not arrays of packages. The
schema previously accepted unsupported package arrays; these now fail validation
explicitly. Put dependencies in the appropriate manifest file instead.

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/validate_catalog.py --no-self-test
```

Regenerate `catalog.json` deliberately with
`python3 scripts/validate_catalog.py --write-catalog --no-self-test` when changing
indexed manifest fields. Run skill self-tests separately with
`python3 scripts/validate_catalog.py` when applicable.

Validation is read-only by default: missing or stale `catalog.json` fails instead
of silently regenerating it. Even `--write-catalog` will not overwrite the index
if manifest validation fails.

## Catalog releases and runtime pins

Production defaults now come from the full catalog commit SHA in the runtime's
`release/manifest.json`; they do not follow template `main`. Template-only changes
can still merge and be published independently. A release promotion is deliberate:

1. Review/merge the catalog change and record its immutable commit SHA. An
   optional human-readable catalog release tag must not be moved or reused.
2. Test that exact templates SHA with the proposed runtime revision through the
   paired workflow. For runtime-dependent content, publish/deploy the compatible
   runtime before users update the template.
3. Update the runtime manifest's templates revision and run
   `make versions-generate` / `make versions-check` there. Its PR tests the pin.
4. Publish through the normal runtime release process. Consumers opt into a newer
   catalog explicitly or receive the tested default in a later runtime release.

Explicit previews can still select `[templates] repo =
"https://github.com/openlia/minions.git"` and `ref = "main"`. Remove an old
`ref = "main"` override to adopt pinned defaults. Custom remotes require a ref.
Never rewrite users' customized installations when promoting a catalog release;
use the normal update/rebase flow.
