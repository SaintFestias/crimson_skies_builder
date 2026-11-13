# ADR-001: Source of truth for aircraft records

Status: Accepted
Date: 2026-11-13

## Context
Aircraft come from two places: template records imported from the 1937 source file, and records users create through the API. Validation rules must apply to both, and the 1937 file should not be edited by the API.

## Decision
- DynamoDB (`aircraft` table) is the source of truth for all live records, template and user-created.
- `data/import/aircraft_of_north_america.json` is a one-time seed. It is not read at runtime and is not updated by the API.
- `src/validators.py` is the only place validation rules live. The batch script and the write Lambda both import it.
- Edit keys live in a separate `aircraft_keys` table, storing SHA-256 hashes only.

## Consequences
- Corrections to template data go through the import script and a re-seed, not through the API.
- Rule changes ship with the code and apply to new writes. Existing records are re-checked by the batch script before any schema change.
- Exports from `aircraft` never contain key material.
