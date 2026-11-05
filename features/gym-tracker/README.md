# Gym & Workout Tracker (`gym-tracker`)

Install `gym-tracker` to add the `minions/gym-tracker` programmable app to your workspace.

- **Code-only distribution**: Fresh installation derives local settings in `minions/gym-tracker/config.json` from `config.schema.json` defaults (`weekly_target_sessions: 3`, `weight_unit: "kg"`) with automatic triggers turned off (`trigger: {"on_new_entry": false}`).
- **Structured input & enrichment**: Log exercises, sets, reps, and weight through `input.openui` / `input.py`, and run `main.py` (`--trigger entry` or `--trigger heartbeat`) to compute progressive overload recommendations and refresh `dashboard.openui`.
- **Briefings & reviews**: The runtime reads the declared `sessions` view in `data.views.json`, never app code or caches. Enable automatic participation locally with `data_views.briefing: ["sessions"]`; it defaults off. Hermes uses `minion_describe` and `minion_query` for read-only access.
