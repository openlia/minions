# OpenLia Minions & Catalog (`https://github.com/openlia/minions.git`)

> Public community catalog of workspace profiles, modular domain features, programmable Minion apps, and workflow skills for [OpenLia](https://github.com/openlia/openlia).

OpenLia starts with an ultra-minimal generic workspace (`AGENTS.md`, `sources/`, and `inbox/ingestion/`). Install only the profiles, domain features, Minions, and skills you need, and customize them while retaining upstream 3-way rebase support. Use inline OpenUI for document views and **Minions** for programmable workspace apps; see [the architecture and migration guide](docs/minions.md).

---

## Repository Structure

```text
openlia/minions
├── catalog.json             # Machine-readable index of profiles, features, and skills
├── feature.schema.json      # JSON Schema for feature.yaml manifests
├── profiles/                # Complete starter profiles (e.g., personal-os)
│   └── personal-os/
│       ├── profile.yaml
│       ├── SOUL.md
│       ├── AGENTS.md
│       └── WORKSPACE_AGENTS.md
├── features/                # Modular domain packages (workspace templates + schemas + OpenUI + Minions + skills)
│   ├── areas/
│   ├── calendar/            # Calendar Minion; requires.tools: ["remind"]
│   ├── claims/
│   ├── daily-briefing/
│   ├── decision-analysis/
│   ├── deep-research/
│   ├── goals/
│   ├── gym-tracker/         # Pilot Minion app (minions/gym-tracker)
│   ├── ideas/
│   ├── monitors/
│   ├── people/
│   ├── personal-finance/    # Minion app + skill; requires.tools: ["hledger"]
│   ├── personal-health/     # Minion app + skill; person-scoped clinical records
│   ├── shopping/
│   ├── tasks/
│   └── travel/
├── skills/                  # Standalone workflow skills
│   ├── calendar/
│   ├── daily-briefing/
│   ├── document-intelligence/
│   ├── inbox-triage/
│   ├── weekly-review/
│   ├── workspace-git/
│   └── workspace-organize/
└── scripts/
    └── validate_catalog.py  # Offline validator for manifests, templates, schemas, and skill self-tests
```

---

## Usage with `openlia` CLI

```bash
# Sync the runtime release's pinned catalog (or your explicit catalog source/ref)
openlia features sync

# List available features and skills
openlia features list
openlia skills list

# Install a feature (automatically provisions required tools like hledger/remind into /opt/data/.local)
openlia features install tasks
openlia features install personal-finance

# Or initialize a deployment with a starter profile
openlia init --local --template personal-os
```

## Validating the Catalog

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/validate_catalog.py
```

See [Contributing](CONTRIBUTING.md) for runtime compatibility requirements,
paired-PR delivery, the one-command integration runner, catalog releases, and
local two-checkout development.
