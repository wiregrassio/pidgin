# Sprint Runner Session — Tooling v0.4

Run the v0.4 sprint.

```
/run-sprint local/sprints/tooling-v0.4/sprint.xml
```

## Decision Point Resolutions

Pass these if prompted, or resolve interactively:

- **DP1:** gpt-5.4-mini fallback if gpt-4.1-mini fails gate probes.
- **DP2:** per-batch upsert (confirmed).
- **DP3:** accept reindex from identity key migration (confirmed).
- **DP4:** M17 conditional on M16 GO with 500+ examples.
- **DP5:** M15 drops first if sprint runs long.

## Commander Watch Items

Surface these to the operator at the relevant mission pause points:

1. **M1 → M3 shared files.** M1 and M3 both modify batch.py and
   index.py. M3 must run after M1 is GREEN. If M3's executor takes
   a backup, it must capture the post-M1 state. If a rollback
   restores pre-M1 code, M1's work is lost. Flag this at the M3
   dispatch pause if the executor's backup step looks wrong.

2. **M5 probe ambiguity.** Probes G3 and G5 share the function name
   "merge" — G3 with a valid description, G5 with a truncated one.
   If the M5 executor's report shows confusion between the two probes,
   note it for the operator.

3. **M6 wall time.** The full SDK index may take 3-5 hours. This is
   expected. Interruptions and resumptions are fine — M1 and M2 exist
   to make this survivable. The success criterion is 500+ converged
   examples, not an uninterrupted run.

4. **M8, M11, M17 require review dispatch.** These have review="true".
   After the executor pass, compose and dispatch the review mission
   per the review template in the run-sprint skill. Do not skip
   reviews on these three.

5. **M15 is deferrable.** If the operator says "drop M15" at any
   point, skip it and note the deferral in log.md.

6. **Phase 5 is conditional.** Only dispatch M16-M18 if M6's log
   entry confirms 500+ converged examples in training-data.jsonl.
   If M6 fell short, report to the operator and skip Phase 5.
