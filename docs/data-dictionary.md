# Data Dictionary

> Canonical field definitions for the Final Whistle data model.
> Updated as the schema evolves.

This document will be populated during Milestone 2 when the database
schema is finalized.

## Conventions

- All primary keys use `id` (UUID or auto-incrementing integer — TBD).
- All timestamps are stored in UTC.
- Provider-specific identifiers are kept in mapping columns/tables.
- Scores distinguish `NULL` (not yet played) from `0` (zero goals).

