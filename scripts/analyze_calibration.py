#!/usr/bin/env python3
"""
Analyze calibration data from calibrate.py.

Questions to answer:
1. Does draft_3 cluster tighter than draft_1? (No — data shows the opposite)
2. Does temperature matter? (Yes — dominant variable)
3. What's the right convergence metric? (sv of draft_1 at low temp)
4. At what N does the metric stabilize? (Subsample from 25 down to 3)
5. What threshold separates "converged" from "not converged"?
6. How many rate limit errors did we hit?
"""

import json
import numpy as np
from collections import defaultdict
from pathlib import Path

DATA_FILE = "calibration-data.json"
VECTORS_FILE = "calibration-vectors.npz"


def load_data():
    with open(DATA_FILE) as f:
        data = json.load(f)
    
    # Reload vectors and reattach
    npz = np.load(VECTORS_FILE)
    vectors = npz["vectors"]
    index = npz["index"]
    
    # Build lookup: (fi, candidate_idx) -> vector
    vec_lookup = {}
    for i, (fi, ci) in enumerate(index):
        vec_lookup[(int(fi), int(ci))] = vectors[i]
    
    # Reattach vectors to candidates
    for rec in data:
        fi = rec["fi"]
        for ci, cand in enumerate(rec["candidates"]):
            key = (fi, ci)
            if key in vec_lookup:
                cand["vector"] = vec_lookup[key].tolist()
            else:
                cand["vector"] = None
    
    return data


def spherical_variance(vectors):
    if len(vectors) < 2:
        return None
    arr = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    unit = arr / norms
    mean_vec = unit.mean(axis=0)
    return float(1.0 - np.linalg.norm(mean_vec))


def analyze_draft_vs_temperature(data):
    """Question 1 & 2: Does draft matter? Does temperature matter?"""
    print("=" * 80)
    print("DRAFT vs TEMPERATURE ANALYSIS")
    print("=" * 80)
    
    temps = [0.3, 0.7, 1.0, 1.5]
    drafts = [1, 2, 3]
    
    # Collect sv values per (temp, draft) across all functions
    sv_by_td = defaultdict(list)
    
    for rec in data:
        for temp in temps:
            for draft in drafts:
                vecs = [c["vector"] for c in rec["candidates"]
                        if c["temp"] == temp and c["draft"] == draft 
                        and c["vector"] is not None]
                if len(vecs) >= 3:
                    sv = spherical_variance(vecs)
                    if sv is not None:
                        sv_by_td[(temp, draft)].append(sv)
    
    print(f"\nMean spherical variance (lower = tighter cluster):")
    print(f"{'':>8}", end="")
    for d in drafts:
        print(f"  draft_{d:>1}", end="")
    print()
    
    for temp in temps:
        print(f"t={temp:<4}", end="")
        for draft in drafts:
            vals = sv_by_td[(temp, draft)]
            if vals:
                print(f"  {np.mean(vals):>7.4f}", end="")
            else:
                print(f"     n/a", end="")
        print()
    
    print(f"\n--- Key finding ---")
    d1_low = np.mean(sv_by_td[(0.3, 1)])
    d3_low = np.mean(sv_by_td[(0.3, 3)])
    d1_high = np.mean(sv_by_td[(1.5, 1)])
    d3_high = np.mean(sv_by_td[(1.5, 3)])
    print(f"t=0.3 draft_1 mean sv: {d1_low:.4f}")
    print(f"t=0.3 draft_3 mean sv: {d3_low:.4f}  ({'WORSE' if d3_low > d1_low else 'BETTER'})")
    print(f"t=1.5 draft_1 mean sv: {d1_high:.4f}")
    print(f"t=1.5 draft_3 mean sv: {d3_high:.4f}  ({'WORSE' if d3_high > d1_high else 'BETTER'})")
    print(f"\nDraft 3 is {'LESS' if d3_low > d1_low else 'MORE'} converged than draft 1.")
    print(f"Temperature effect: {d1_high/d1_low:.1f}x variance from t=0.3 to t=1.5")


def analyze_optimal_temperature(data):
    """Find the best temperature for convergence."""
    print("\n" + "=" * 80)
    print("OPTIMAL TEMPERATURE")
    print("=" * 80)
    
    temps = [0.3, 0.7, 1.0, 1.5]
    
    # For each function, compute sv at draft_1 for each temperature
    results = {t: [] for t in temps}
    
    for rec in data:
        for temp in temps:
            vecs = [c["vector"] for c in rec["candidates"]
                    if c["temp"] == temp and c["draft"] == 1 
                    and c["vector"] is not None]
            if len(vecs) >= 5:
                sv = spherical_variance(vecs)
                if sv is not None:
                    results[temp].append({"name": rec["name"], "sv": sv})
    
    print(f"\nDistribution of sv (draft_1) by temperature:")
    print(f"{'temp':>6} {'mean':>8} {'median':>8} {'p10':>8} {'p90':>8} {'min':>8} {'max':>8} {'n':>5}")
    for temp in temps:
        vals = [r["sv"] for r in results[temp]]
        if vals:
            arr = np.array(vals)
            print(f"t={temp:<4} {np.mean(arr):>8.4f} {np.median(arr):>8.4f} "
                  f"{np.percentile(arr, 10):>8.4f} {np.percentile(arr, 90):>8.4f} "
                  f"{np.min(arr):>8.4f} {np.max(arr):>8.4f} {len(vals):>5}")


def analyze_subsample_stability(data):
    """Question 4: At what N does sv stabilize? Subsample from 25 down."""
    print("\n" + "=" * 80)
    print("SUBSAMPLE STABILITY (t=0.3, draft_1)")
    print("=" * 80)
    
    sample_sizes = [3, 5, 7, 10, 15, 20, 25]
    n_trials = 50  # repeat each subsample this many times
    
    # Collect all draft_1, t=0.3 vectors per function
    func_vecs = {}
    for rec in data:
        vecs = [c["vector"] for c in rec["candidates"]
                if c["temp"] == 0.3 and c["draft"] == 1 
                and c["vector"] is not None]
        if len(vecs) >= 25:
            func_vecs[rec["name"]] = vecs
    
    print(f"\n{len(func_vecs)} functions with 25+ vectors at t=0.3 draft_1")
    print(f"\nMean sv across {n_trials} random subsamples per N:")
    print(f"{'N':>5} {'mean_sv':>10} {'std_sv':>10} {'cv':>10} {'stable':>8}")
    
    reference_svs = {}
    for name, vecs in func_vecs.items():
        reference_svs[name] = spherical_variance(vecs)
    
    for n in sample_sizes:
        deviations = []
        sv_values = []
        for name, vecs in func_vecs.items():
            ref = reference_svs[name]
            for _ in range(n_trials):
                idx = np.random.choice(len(vecs), size=n, replace=False)
                subset = [vecs[i] for i in idx]
                sv = spherical_variance(subset)
                sv_values.append(sv)
                deviations.append(abs(sv - ref))
        
        arr = np.array(sv_values)
        dev = np.array(deviations)
        cv = np.std(arr) / np.mean(arr) if np.mean(arr) > 0 else float('inf')
        stable = "YES" if cv < 0.15 else ("MAYBE" if cv < 0.25 else "NO")
        print(f"{n:>5} {np.mean(arr):>10.4f} {np.std(arr):>10.4f} {cv:>10.4f} {stable:>8}")
    
    print(f"\nMean absolute deviation from N=25 reference:")
    print(f"{'N':>5} {'mean_dev':>10} {'max_dev':>10}")
    for n in sample_sizes:
        if n == 25:
            continue
        devs = []
        for name, vecs in func_vecs.items():
            ref = reference_svs[name]
            for _ in range(n_trials):
                idx = np.random.choice(len(vecs), size=n, replace=False)
                subset = [vecs[i] for i in idx]
                sv = spherical_variance(subset)
                devs.append(abs(sv - ref))
        print(f"{n:>5} {np.mean(devs):>10.4f} {np.max(devs):>10.4f}")


def analyze_threshold(data):
    """Question 5: What threshold works?"""
    print("\n" + "=" * 80)
    print("THRESHOLD ANALYSIS (t=0.3, draft_1, all 25 calls)")
    print("=" * 80)
    
    results = []
    for rec in data:
        vecs = [c["vector"] for c in rec["candidates"]
                if c["temp"] == 0.3 and c["draft"] == 1 
                and c["vector"] is not None]
        if len(vecs) >= 5:
            sv = spherical_variance(vecs)
            if sv is not None:
                results.append({"name": rec["name"], "sv": sv, "body_len": rec.get("body_len", 0)})
    
    results.sort(key=lambda x: x["sv"])
    
    print(f"\nAll {len(results)} functions ranked by sv (ascending = tightest):")
    print(f"{'sv':>8} {'body':>6} {'name':<50}")
    for r in results:
        marker = ""
        if r["sv"] < 0.02:
            marker = " *** trivial"
        elif r["sv"] < 0.05:
            marker = " ** tight"
        elif r["sv"] < 0.10:
            marker = " * good"
        elif r["sv"] > 0.15:
            marker = " ! loose"
        print(f"{r['sv']:>8.4f} {r['body_len']:>6} {r['name']:<50}{marker}")
    
    print(f"\nThreshold analysis:")
    for threshold in [0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20]:
        n_pass = sum(1 for r in results if r["sv"] < threshold)
        print(f"  sv < {threshold:.2f}: {n_pass}/{len(results)} converged ({100*n_pass/len(results):.0f}%)")
    
    # Correlation with body length
    svs = np.array([r["sv"] for r in results])
    lens = np.array([r["body_len"] for r in results])
    corr = np.corrcoef(svs, lens)[0, 1]
    print(f"\nCorrelation sv vs body_length: {corr:.3f}")


def analyze_pooled_vs_stratified(data):
    """Compare: pool all 75 candidates (25 calls × 3 drafts) vs draft_1 only."""
    print("\n" + "=" * 80)
    print("POOLED (all drafts) vs DRAFT_1 ONLY (t=0.3)")
    print("=" * 80)
    
    results = []
    for rec in data:
        all_vecs = [c["vector"] for c in rec["candidates"]
                    if c["temp"] == 0.3 and c["vector"] is not None]
        d1_vecs = [c["vector"] for c in rec["candidates"]
                   if c["temp"] == 0.3 and c["draft"] == 1 
                   and c["vector"] is not None]
        if len(all_vecs) >= 10 and len(d1_vecs) >= 5:
            sv_all = spherical_variance(all_vecs)
            sv_d1 = spherical_variance(d1_vecs)
            results.append({
                "name": rec["name"],
                "sv_pooled": sv_all,
                "sv_d1": sv_d1,
                "n_pooled": len(all_vecs),
                "n_d1": len(d1_vecs),
            })
    
    print(f"\n{'name':<40} {'sv_pool':>8} {'sv_d1':>8} {'diff':>8}")
    for r in sorted(results, key=lambda x: x["sv_d1"]):
        diff = r["sv_pooled"] - r["sv_d1"]
        print(f"{r['name']:<40} {r['sv_pooled']:>8.4f} {r['sv_d1']:>8.4f} {diff:>+8.4f}")
    
    pool_mean = np.mean([r["sv_pooled"] for r in results])
    d1_mean = np.mean([r["sv_d1"] for r in results])
    print(f"\nMean sv pooled: {pool_mean:.4f}")
    print(f"Mean sv d1:     {d1_mean:.4f}")
    print(f"Pooled is {'WORSE' if pool_mean > d1_mean else 'BETTER'} (includes noisier draft 2/3)")


def analyze_cross_temperature(data):
    """What if we pool across temperatures? Does diversity help or hurt?"""
    print("\n" + "=" * 80)
    print("CROSS-TEMPERATURE POOLING (draft_1 only)")
    print("=" * 80)
    
    results = []
    for rec in data:
        low_vecs = [c["vector"] for c in rec["candidates"]
                    if c["temp"] == 0.3 and c["draft"] == 1 
                    and c["vector"] is not None]
        all_temp_vecs = [c["vector"] for c in rec["candidates"]
                        if c["draft"] == 1 and c["vector"] is not None]
        if len(low_vecs) >= 5 and len(all_temp_vecs) >= 20:
            sv_low = spherical_variance(low_vecs)
            sv_all = spherical_variance(all_temp_vecs)
            results.append({
                "name": rec["name"],
                "sv_t03": sv_low,
                "sv_all_temps": sv_all,
                "n_t03": len(low_vecs),
                "n_all": len(all_temp_vecs),
            })
    
    t03_mean = np.mean([r["sv_t03"] for r in results])
    all_mean = np.mean([r["sv_all_temps"] for r in results])
    print(f"\nMean sv t=0.3 only:    {t03_mean:.4f} (N~25)")
    print(f"Mean sv all temps:     {all_mean:.4f} (N~100)")
    print(f"Mixing temperatures {'HURTS' if all_mean > t03_mean else 'HELPS'} convergence")


def count_errors(data):
    """Count dropped candidates from rate limits and parse errors."""
    print("\n" + "=" * 80)
    print("ERROR ANALYSIS")
    print("=" * 80)
    
    expected = len(data) * 4 * 25 * 3  # functions × temps × calls × drafts
    actual = sum(len(rec["candidates"]) for rec in data)
    missing = expected - actual
    
    # Count by temperature
    by_temp = defaultdict(int)
    for rec in data:
        for temp in [0.3, 0.7, 1.0, 1.5]:
            count = len([c for c in rec["candidates"] if c["temp"] == temp])
            by_temp[temp] += count
    
    expected_per_temp = len(data) * 25 * 3
    print(f"\nExpected total candidates: {expected}")
    print(f"Actual candidates:        {actual}")
    print(f"Missing (errors):         {missing} ({100*missing/expected:.1f}%)")
    print(f"\nBy temperature:")
    for temp in [0.3, 0.7, 1.0, 1.5]:
        lost = expected_per_temp - by_temp[temp]
        print(f"  t={temp}: {by_temp[temp]}/{expected_per_temp} ({100*lost/expected_per_temp:.1f}% lost)")


def main():
    print("Loading calibration data...")
    data = load_data()
    print(f"Loaded {len(data)} functions\n")
    
    count_errors(data)
    analyze_draft_vs_temperature(data)
    analyze_optimal_temperature(data)
    analyze_pooled_vs_stratified(data)
    analyze_cross_temperature(data)
    analyze_subsample_stability(data)
    analyze_threshold(data)
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print("""
Based on the data:

1. USE DRAFT_1 ONLY. Draft 2/3 increase variance, not decrease it.
   The token compression forces divergent choices about what to include.

2. USE TEMPERATURE 0.3. It produces the tightest clusters. Higher temps
   add noise without adding signal for convergence detection.

3. THRESHOLD: Pick from the analysis above based on your tolerance.
   Look at the ranked function list — where do "obviously correct" 
   descriptions end and "questionable" ones begin?

4. MINIMUM N: Read the subsample stability section. The N where 
   coefficient of variation drops below 0.15 is your minimum.

5. RATE LIMIT HANDLING: Add exponential backoff with jitter.
   The 200K TPM ceiling hit ~30 times during this run. A 1-2 second
   sleep after 429 errors would catch most cases.
""")


if __name__ == "__main__":
    main()
