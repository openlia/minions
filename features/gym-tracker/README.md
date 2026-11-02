# Gym & Workout Tracker (`gym-tracker`)

Install `gym-tracker` to add the `minions/gym-tracker` programmable app to your workspace.

- **Code-only distribution**: Fresh installation derives local settings in `minions/gym-tracker/config.json` from `config.schema.json` defaults (`weekly_target_sessions: 3`, `weight_unit: "kg"`) with automatic triggers turned off (`trigger: {"on_new_entry": false}`).
- **Structured input & enrichment**: Log exercises, sets, reps, and weight through `input.openui` / `input.py`, and run `main.py` (`--trigger entry` or `--trigger heartbeat`) to compute progressive overload recommendations and refresh `dashboard.openui`.
- **Briefings & reviews**: App internals under `minions/gym-tracker/` are excluded from generic briefing discovery. Publish intentional, dated Markdown workout summaries outside `minions/` when you want them included in daily briefings or weekly reviews.
