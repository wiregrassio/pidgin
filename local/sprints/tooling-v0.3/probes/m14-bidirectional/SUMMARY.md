# M15 Bidirectional Probe Results

| Probe | Budget | Run | cluster_size | syn_valid | converged |
|-------|--------|-----|--------------|-----------|-----------|
| P1_embed_for_store | 50 | 0 | 6 | 7/10 | true |
| P1_embed_for_store | 50 | 1 | 4 | 4/10 | false |
| P1_embed_for_store | 50 | 2 | 7 | 4/10 | true |
| P1_embed_for_store | 200 | 0 | 6 | 10/10 | true |
| P1_embed_for_store | 200 | 1 | 5 | 10/10 | false |
| P1_embed_for_store | 200 | 2 | 5 | 10/10 | false |
| P2_main | 50 | 0 | 6 | 0/10 | true |
| P2_main | 50 | 1 | 7 | 0/10 | true |
| P2_main | 50 | 2 | 7 | 0/10 | true |
| P2_main | 200 | 0 | 6 | 9/10 | true |
| P2_main | 200 | 1 | 6 | 9/10 | true |
| P2_main | 200 | 2 | 4 | 10/10 | false |
| P3_apply | 50 | 0 | 8 | 0/10 | true |
| P3_apply | 50 | 1 | 10 | 0/10 | true |
| P3_apply | 50 | 2 | 10 | 0/10 | true |
| P3_apply | 200 | 0 | 9 | 10/10 | true |
| P3_apply | 200 | 1 | 9 | 10/10 | true |
| P3_apply | 200 | 2 | 8 | 10/10 | true |
| P4_merge | 50 | 0 | 8 | 10/10 | true |
| P4_merge | 50 | 1 | 8 | 10/10 | true |
| P4_merge | 50 | 2 | 5 | 10/10 | false |
| P4_merge | 200 | 0 | 8 | 10/10 | true |
| P4_merge | 200 | 1 | 7 | 10/10 | true |
| P4_merge | 200 | 2 | 7 | 10/10 | true |
| P5_antipode_test | 50 | 0 | 6 | 0/10 | true |
| P5_antipode_test | 50 | 1 | 6 | 0/10 | true |
| P5_antipode_test | 50 | 2 | 7 | 0/10 | true |
| P5_antipode_test | 200 | 0 | 6 | 0/10 | true |
| P5_antipode_test | 200 | 1 | 6 | 0/10 | true |
| P5_antipode_test | 200 | 2 | 5 | 0/10 | false |

## Aggregates

- Total runs: 30
- Runs with converged=true: 24/30
- Per-probe stability (converged runs out of 6): P1=3/6, P2=5/6, P3=6/6, P4=5/6, P5=5/6
- Mean cluster_size by budget: 50=7.0, 200=6.5
- Syntactic validity rate: 5.4/10 mean per run
- Wall time: 325.4s (two mega-batches: 174s gen + 152s embed)
- Cost reported: estimated ~$0.030 (300 gen calls @ gpt-4.1-nano batch + 300 embed calls)
