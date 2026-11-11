# ADR-001: Source of truth for aircraft data

**Status:** Proposed
**Date:** 2026-11-11
**Deciders:** [your name]

## Context

Aircraft data exists as a Markdown file and a JSON file with identical content. The platform will create and edit aircraft through an API, so the data needs one authoritative location. Two editable copies would drift apart, and a Slack notification could report values that no longer match the export.

## Decision drivers

- Edits happen through the API, so writes must be validated and versioned.
- Exports should be machine-readable and diffable in git.
- The Markdown file is for humans to read and should not be parsed as data.
- The import should be repeatable so the data can be rebuilt from scratch.

## Options considered

1. **JSON file in git as source.** Validated against the schema in CI. Simple, but the API needs a second write path to git, which couples runtime writes to a repo.
2. **Markdown as source.** Readable, but parsing tables and stat blocks is fragile, and the Markdown has no schema.
3. **Database as source, JSON and Markdown generated.** The API writes to Postgres, and an export job produces the JSON (schema-validated) and Markdown (for reading). Requires an export step, but the runtime has one write path.
4. **Keep both files in sync manually.** Rejected: guaranteed drift.

## Decision

Option 3. The database is the source of truth once the initial import runs. The JSON export, validated against `schema_version: 1`, is the canonical interchange format. The Markdown file is a generated view and is never edited by hand.

## Consequences

Positive: one write path, versioned records (`version` column), and a clear export contract for other tools.

Negative: a bootstrap import is needed, the export job must run after every change, and the Markdown view can lag if the job fails. Mitigate by making export part of the same outbox event flow.

## Follow-up

- ADR-002: normalized tables vs. JSONB for weapons and armor.
- ADR-003: outbox vs. direct Slack call from the API.
