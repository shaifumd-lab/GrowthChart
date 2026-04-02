# CDS Phrasing Rules — Changelog v2.0

**Based on:** Dr. Shai Fuchs clinical review feedback  
**Applied to:** `growth_cds_matrix.html` → `growth_cds_matrix_v2.html`

---

## Rule-by-Rule Changes

### R1: Flag Patterns, Never Diagnose

| Location | Before (v1) | After (v2) | Rationale |
|----------|-------------|------------|-----------|
| **Category: Cushing's** | `CUSHING'S SCREENING` | `DIVERGENT WEIGHT–HEIGHT TRAJECTORY` | Pattern name, not diagnosis |
| Category items | "Cushing's screening workup" / "Cushing's syndrome suspected" | "Divergent trajectory — evaluate" / "Divergent trajectory with abnormal cortisol" | All 4 tiers rewritten |
| **Category: Turner** | `TURNER SYNDROME (FEMALES)` | `UNEXPLAINED SHORT STATURE — FEMALES` | Karyotype is a standard workup step, not a diagnostic label |
| Category items | "Turner features present" / "Turner confirmed" | "Short stature in female with additional features — evaluate" / "Chromosomal finding confirmed" | Pattern-first language |
| **Category: Thyroid/Celiac** | `THYROID / CELIAC SCREENING` | `GROWTH DECELERATION — METABOLIC SCREEN` | Screen triggered by growth pattern, not by suspected diagnosis |
| **Category: Puberty** | `PRECOCIOUS / DELAYED PUBERTY` | `ATYPICAL PUBERTAL TIMING` | Timing pattern, not diagnostic label |
| Puberty Tier 3 | "Probable precocious or delayed puberty" | "Atypical pubertal timing pattern — evaluate" | |
| Puberty Tier 4 | "Confirmed precocious / gonadotropin-independent" | "Urgent pubertal timing pattern — immediate evaluation" | |
| **Tall stature Tier 3** | "Pathologic tall stature workup" | "Accelerated tall stature pattern — evaluate" | |
| **Tall stature Tier 4** | "Suspected Marfan" / "GH-secreting pituitary adenoma" in trigger | "Connective tissue features (aortic root risk)" / "suspected pituitary pathology" | Pattern descriptions |
| **Obesity Tier 3** | "Cushing's flag" in trigger | "DIVERGENT FLAG" — cross-references divergent trajectory pathway | |
| **Obesity Tier 4** | "Severe obesity / Cushing's flag" | "Severe excess weight / divergent trajectory — urgent evaluation" | |
| **Crossing Tier 3 orders** | "Divergent: Cushing's screen" | "Divergent trajectory: cortisol evaluation" | |
| **Crossing Tier 4 notes** | "acquired hypothyroidism, GHD, craniopharyngioma, celiac" | "evaluate acquired endocrine, autoimmune, CNS" | Pattern categories |
| **Bone age Tier 3 notes** | "Delayed BA: GHD, hypothyroidism, celiac. Advanced BA: precocious puberty, CAH." | "R1: workup direction determined by pattern, not pre-assigned diagnosis." | |
| **Order set** | "Cushing's Screen" | "Divergent Trajectory Workup (Cortisol Evaluation)" | |
| **Order set** | "Turner Syndrome Workup" | "Female Short Stature — Chromosomal Workup" | |
| **Order set** | "Precocious Puberty Workup" | "Atypical Pubertal Timing — Early Workup" | |
| **Order set** | "Delayed Puberty Workup" | "Atypical Pubertal Timing — Late Workup" | |
| **Order set** | "GH Stimulation Referral Bundle" | "Severe Short Stature Referral Bundle" | |
| **All Tier 3 physician text** | Various ("Full workup", "Consider referral") | Standardized: "Pattern warrants evaluation — [specific workup]" | R5 also |
| **All Tier 4 physician text** | Various ("Urgent referral", "Refer to...") | Standardized: "Urgent pattern — immediate [specialty] evaluation recommended" | R5 also |
| **Filter buttons** | "Cushing's" / "Turner" / "Thyroid/Celiac" / "FTT" | "Wt↑ / Ht↓" / "♀ Short Stature" / "Metabolic Screen" / "Weight Faltering" | UI labels |
| **FTT category** | "FAILURE TO GAIN WEIGHT / FTT" | "WEIGHT FALTERING / POOR WEIGHT GAIN" | Pattern description |
| **Obesity category** | "OBESITY" | "EXCESS WEIGHT GAIN" | |
| **Crossing category** | "PERCENTILE CROSSING" | "GROWTH TRAJECTORY CHANGE" | Emphasizes trajectory |
| **Parent messaging** | "Test results suggest a cortisol problem" | "Test results indicate a hormonal pattern needing specialist evaluation" | |

### R2: Don't Assume Data Exists

| Location | Before (v1) | After (v2) |
|----------|-------------|------------|
| **All puberty tiers** | Triggers directly reference Tanner staging without checking if recorded | Triggers now begin with `IF Tanner data recorded:` conditional |
| **Puberty Tier 2** | "no puberty by 12 (girls) / 13 (boys)" triggers directly | If Tanner NOT recorded AND age threshold → flags: "Pubertal staging not documented — consider assessment" |
| **Puberty Tier 3** | "Tanner ≥2 before 7" triggers directly | Only fires if Tanner data explicitly present. If absent at age >13/14 → "Pubertal staging not documented at age [X] — assessment recommended" |
| **Puberty Tier 4** | Could escalate without confirmed data | Now requires: "Tier 4 requires confirmed Tanner staging AND lab results. Do not escalate on missing data alone." |
| **New field: `dataReq`** | Not present | Added `dataReq` field to every item. Shows orange "DATA REQUIREMENT" badge when data prerequisites exist |
| **Short stature Tier 2** | No data requirement noted | "Requires ≥2 height measurements ≥3 mo apart for GV" |
| **Short stature Tier 3** | No data requirement | "Requires ≥6 mo growth data for GV. PAH requires bone age." |
| **Short stature Tier 4** | No data requirement | "Requires ≥12 mo growth data for sustained GV <5th" |
| **Divergent Tier 2** | No data requirement | "Requires ≥6 mo of both weight AND height z-scores" |
| **Divergent Tier 3** | No data requirement | "Requires confirmed height deceleration (≥2 measurements showing declining GV) concurrent with weight gain" |
| **Divergent Tier 4** | No data requirement | "Requires ≥2 abnormal cortisol screening results" |
| **SGA Tier 1** | No data requirement | "Requires confirmed birth weight/length and gestational age" |
| **Puberty threshold notes** | No data flag | Added `*` footnote: "ONLY if Tanner staging documented. If absent → flag missing data" |

### R3: Trajectories Matter More Than Thresholds

| Location | Before (v1) | After (v2) |
|----------|-------------|------------|
| **New threshold row** | Not present | `Weight z-delta /6 mo`: Tier 1 ≤0.5, Tier 2 >0.5, Tier 3 >1.0, Tier 4 >2.0 SD |
| **Renamed threshold row** | `Z-score Δ /12 mo` (generic) | `Height z-delta /12 mo` (explicit) |
| **New threshold row** | Not present | `Trajectory divergence (wt↑ ht↓)`: Concordant → Weight↑ height stable → Weight↑ height↓ confirmed → Divergent + abnormal cortisol |
| **Short stature triggers** | Only absolute z-scores | Added `height z-delta >X SD decline over 12 mo` to Tiers 2/3/4 |
| **Obesity triggers** | Only BMI %ile | Added `weight z-delta >X SD increase over 12 mo` to Tiers 2/3/4 |
| **Weight faltering triggers** | Only absolute %ile | Added `weight z-delta >X SD decline over 6 mo` to Tiers 2/3/4 |
| **Tall stature triggers** | Only absolute | Added `upward height z-delta` to Tiers 2/3 |
| **Crossing Tier 3 notes** | "Divergent trajectories... = highest-yield red flag for endocrine pathology" | Elevated to main physician text with direction-specific workup guidance |
| **All `params` fields** | Omitted z-delta | Added `z-delta`, `wt z-delta`, `ht z-delta` to params where trajectory is monitored |
| **Divergent category** | Existed as "Cushing's" (threshold-based) | Completely rebuilt as trajectory-based category with wt z-delta and ht z-delta as primary parameters |
| **Metabolic screen Tier 2** | "Any growth deceleration" | Added: "height z-delta >0.5 SD decline with no other explanation" |

### R4: Use Standard Clinical Thresholds

| Parameter | Before (v1) | After (v2) | Standard |
|-----------|-------------|------------|----------|
| **Height z Tier 3 entry** | "-2.0 to -2.25 SD" (ambiguous) | `≤ -2.0 SD` | Standard short stature workup threshold |
| **Height z Tier 4 entry** | "< -2.25 SD" | `≤ -2.25 SD` (kept) | ISS / FDA GH threshold |
| **All threshold operators** | Range notation ("1.5–2.5 yr") | Explicit operators (`> 1.5 yr`) | Eliminates boundary ambiguity |
| **Bone age delay Tier 3** | "1.5–2.5 yr" | `> 1.5 yr` | Exactly 1.5 yr → Tier 3 |
| **Bone age advance Tier 3** | "1.5–2.5 yr" | `> 1.5 yr` | Same fix |
| **Weight-for-length Tier 3** | "-2.0 to -3.0" | `< -2.0 SD` | WHO moderate wasting |
| **BMI Tier 2** | "85th–94th" | `≥ 85th` | AAP standard |
| **Puberty ♂ Tier 4 late** | "> 15" | `≥ 15` | Explicit boundary |
| **Threshold table** | Mixed range/operator notation | All cells use explicit `≤`, `≥`, `>`, `<` operators | Unambiguous for implementation |

### R5: Tier Language — Action-Oriented

| Tier | Before (v1) | After (v2) |
|------|-------------|------------|
| **Tier 2 label** | "Observe" | "Monitor Pattern" |
| **Tier 3 label** | "Evaluate" | "Pattern Warrants Evaluation" |
| **Tier 4 label** | "Act/Refer" | "Urgent Pattern / Refer" |
| **Tier 3 physician text pattern** | Various: "Full workup", "Consider referral", "Screen for X" | Standardized: **"Pattern warrants evaluation — [workup description]"** |
| **Tier 4 physician text pattern** | Various: "Urgent referral", "Refer to endocrinology" | Standardized: **"Urgent pattern — immediate [specialty] evaluation recommended"** |
| **Tier 3 threshold header** | "Tier 3 (Evaluate)" | "Tier 3 (Evaluate)" (kept for brevity) |
| **Tier 4 threshold header** | "Tier 4 (Act/Refer)" | "Tier 4 (Urgent)" |
| **Cushing's physician Tier 1** | "No Cushing's concern" | "No divergent pattern. No concern." |

---

## Structural Changes

1. **New `dataReq` field** on every DATA item — renders as orange "DATA REQUIREMENT" badge in expanded card view. Empty string = no requirement shown.

2. **New category: `divergent`** — "DIVERGENT WEIGHT–HEIGHT TRAJECTORY" replaces "CUSHING'S SCREENING". Same clinical content but framed as trajectory pattern with explicit data requirements.

3. **Renamed category: `female_short`** — "UNEXPLAINED SHORT STATURE — FEMALES" replaces "TURNER SYNDROME (FEMALES)". Karyotype positioned as standard workup step.

4. **Renamed category: `metabolic`** — "GROWTH DECELERATION — METABOLIC SCREEN" replaces "THYROID / CELIAC SCREENING".

5. **New threshold rows:** `Weight z-delta /6 mo` and `Trajectory divergence (wt↑ ht↓)` added to support R3.

6. **Phrasing rules banner** appears at top of Decision Matrix tab and Thresholds tab for visibility.

7. **Version tag** in header bar: "v2.0 — Phrasing rules applied"

---

## What Did NOT Change

- Lab panels and specific order content (unchanged — these are clinical, not phrasing)
- Parent messaging tone (kept warm and non-diagnostic, already aligned with R1)
- Recheck intervals (unchanged)
- Fundamental tier architecture (4 tiers, same escalation logic)
- SGA pathway (already pattern-based, minimal changes)
- Disproportion pathway (already pattern-based, minor name updates)
- Bone age pathway (already pattern-based, added R1 note to Tier 3)
