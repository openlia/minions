---
name: Gym Tracker
description: Log workout sessions, track progressive overload, and review weekly volume.
icon: dumbbell
---

# Gym Tracker

Programmable workout tracker Minion (`openlia://minions/gym-tracker`).

## Files

- `dashboard.openui`: Workout volume summary, recommendations, and session log table.
- `input.openui` & `input.schema.json`: Validated workout entry form (`item`, `category`, `sets`, `reps`, `value`, `status`, `notes`).
- `config.schema.json`: Recipient configuration schema (`trigger`, `weekly_target_sessions`, `weight_unit`).
- `input.py` & `main.py`: Entry recorder and dual-triggered (`--trigger entry` / `--trigger heartbeat`) analysis engine.
- `tests/test_main.py`: Offline unit tests for input validation, configuration defaults, and OpenUI rendering.
