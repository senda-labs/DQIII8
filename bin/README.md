# bin/ — DQ Scripts

## Current structure (flat)
All scripts are in bin/ for backward compatibility.

## Planned structure (post-beta)
When we reorganize, scripts will move to:

- **core/** — orchestrator, routing, database, config
  - db.py, embeddings.py, notify.py, openrouter_wrapper.py, validate_env.py
- **agents/** — agent definitions and routing
  - domain_classifier.py, knowledge_indexer.py
- **monitoring/** — audit, metrics, subscription
  - auditor.py, subscription.py, system_profile.py, energy_tracker.py, telemetry.py
- **tools/** — utilities and standalone tools
  - paper_harvester.py, knowledge_upload.py, reconcile_errors.py, auto_learner.py, template_loader.py
- **ui/** — dashboard and bot
  - dashboard.py, dashboard.html, login.html, dashboard_security.py, jarvis_bot.py
- **legacy/** — deprecated scripts (already exists)

## Import convention
All scripts use: `sys.path.insert(0, str(JARVIS / "bin"))` for imports.
After reorganization, we'll use proper Python packages with __init__.py.
