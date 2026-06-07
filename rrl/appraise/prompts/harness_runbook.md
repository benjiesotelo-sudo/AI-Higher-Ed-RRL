# MMAT Harness Runbook (operator procedure)

This is the **default engine** for MMAT classify/rate. There is no Python that calls a model on
this path — the **work file is the seam**.

## Loop

1. **Emit.** e.g. `rrl appraise classify --emit batch.work.jsonl --pass 1 --only-sample pilot`.
   Each line of `batch.work.jsonl` is one paper and carries: `work_id`, `paper_id`, `task`,
   `pass`, `prompt_version`, the full `prompt` to follow, and the `schema` the answer must match.

2. **Answer.** For each line, follow its `prompt` exactly and produce the answer:
   - `classify`: ONE JSON object for that paper.
   - `rate`: ONE JSON object PER CRITERION (JSON Lines) for that paper.
   Echo the line's `work_id` on every answer object.

3. **Collect.** Append every answer object as one line to `batch.answers.jsonl`.

4. **Import.** e.g. `rrl appraise classify --import batch.answers.jsonl --work batch.work.jsonl`.
   Import does ALL validation (work_id membership, enums, verbatim `quote_present` check) and UPSERTs.

## Notes

- One model call per paper for `classify`; one per paper for `rate` (all its criteria together).
- **Partial output is fine:** import persists valid lines and leaves the rest pending, so just
  re-emit and continue. `emit` is the single source of truth for what is still pending.
- **Never write the database directly** — only the import step persists.
- Batches of ~100–200 lines per run keep within the harness concurrency cap.
- Two passes use different framings (pass 1 = criterion-first checklist; pass 2 = narrative-then-rate);
  run pass 1 and pass 2 as separate emit/answer/import cycles.
