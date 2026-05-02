"""Admin action endpoint routers (server-action-endpoints capability).

Each sub-module exposes a FastAPI ``APIRouter`` mounted by ``api/app.py``:

- ``screener`` — POST /api/admin/screener/run
- ``confirm_gate`` — GET /api/admin/confirm-gate/pending + 3 POST endpoints
- ``exit_engine`` — POST /api/admin/exit-engine/run

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""
