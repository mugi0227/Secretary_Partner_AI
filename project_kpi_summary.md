# Project KPI work summary

## Backend
- Added KPI models (`ProjectKpiMetric`, `ProjectKpiConfig`, `ProjectKpiTemplate`) and a template catalog.
- Added `GET /api/projects/kpi-templates` to surface KPI templates.
- Added `kpi_config` JSON column to projects and wired it through repository create/update.
- Project schemas now accept `kpi_config` on create/update.

## Frontend
- Added KPI-related types and template API call in the projects client.
- Project detail modal now supports viewing and editing KPI strategy, templates, and metrics.
- Project creation modal now supports configuring KPI strategy, templates, and metrics.
- Added KPI layout styling for the project detail modal.

## Notes
- Existing SQLite DB files need a migration (or a rebuild) to add `projects.kpi_config`.
