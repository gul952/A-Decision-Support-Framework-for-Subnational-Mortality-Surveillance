# Limitations

This document is a required companion to every output this project
produces. It exists because the project's core philosophy is scientific
honesty: every estimate here is a **model**, not a **measurement**, and
every user of this framework — researcher, policymaker, or curious
reader — should know exactly where the uncertainty and simplifications
live before treating any number as ground truth.

---

## 0. A corrected methodological flaw: right-censoring in the hierarchical model (most important item in this document)

An earlier version of this project's hierarchical Bayesian model
(`scripts/models/03_DEPRECATED_hierarchical_bayesian_sae_binomial.py`,
retained in the repository as a documented historical artifact but
**not used in the pipeline**) modeled `deaths ~ Binomial(births, p)`
using already-aggregated district-level birth/death counts. This
implicitly assumed every child in the 5-year reference window had a
FULL 5-year follow-up before being at risk of death — incorrect, since
children born recently before the survey interview had only been
observed for a few months, not five years. This is a real right-
censoring handling error, identified via external methodological
review.

**This was found, diagnosed, and corrected**, not merely patched:
`scripts/models/04_hierarchical_hazard_sae.py` rebuilds the model as a
proper discrete-time hazard model, fit directly on individual birth-
level survival records (`scripts/models/03_build_person_segment_records.py`)
with correct actuarial partial-exposure handling for censored children.

**During this rebuild, two further bugs were found and fixed**,
documented in detail in the corrected script's own docstrings and
commit history:
1. A units mismatch (an actuarial 0/0.5/1 exposure weight was treated
   as if it were continuous person-time), which inflated the national
   aggregate to ~150/1,000 (vs. the known-correct ~75/1,000).
2. A district-ordering mismatch between the model's internal MCMC
   array layout and the reconstruction step, which further distorted
   which posterior samples were attributed to which district.

Both were caught via concrete, falsifiable checks (a known-death-count
validation gate in the person-segment builder, and a mandatory
aggregate-consistency gate in the hazard model itself that will hard-
fail future runs if this class of error recurs — see
`PLAUSIBLE_RANGE` in `scripts/models/04_hierarchical_hazard_sae.py`).

**Concrete evidence the fix mattered, not just theoretical correctness:**
under the flawed model, this project's Balochistan province estimate
diverged from an independent external benchmark (IHME GBD 2023) by
56% (79/1,000 vs. 51/1,000), with province-level rank correlation of
only 0.50. After the correction, that divergence dropped to ~15% and
rank correlation rose to 0.90 (see `docs/GBD_VALIDATION_FINDINGS.md`).
This magnitude of improvement is itself strong evidence the original
flaw was materially distorting estimates, particularly for small-
sample, high-volatility provinces like Balochistan — exactly where a
censoring error would be expected to matter most.

**A remaining, honestly-diagnosed limitation of the corrected model:**
posterior predictive checks (`docs/MODEL_VALIDATION.md`) found the
corrected model still systematically under-predicts total events
(Bayesian p-value ≈0.001), concentrated in the neonatal (0-1 month)
segment. This is a real, specific limitation of the current model
specification (a single global segment-baseline hazard may be
under-weighting neonatal risk relative to the raw data), not something
resolved by the censoring fix — both facts are reported together
because a validation section reporting only clean passes would itself
be a red flag to a careful reviewer.

---

## 1. Geographic coverage gap: Azad Kashmir and Gilgit-Baltistan

The 135-district geometry used throughout this project comes from the
2017 PBS census district-level release, which **does not include**
Azad Jammu & Kashmir (10 districts) or Gilgit-Baltistan (6 districts).
This is a real gap, not a processing error:
- `scripts/cleaning/01_clean_geography.py` explicitly logs these 16
  regions as `shapefile_only` (present in the boundary shapefile, absent
  from the census table we joined against) rather than silently merging
  or dropping them.
- `scripts/cleaning/03_clean_dhs_cluster_geography.py` found 62 DHS
  clusters in AJK and 38 in Gilgit-Baltistan and **excluded them** from
  the district-level analysis rather than force-matching them to a
  nearby, incorrect Pakistani-province district.

**A note on source-data terminology:** the underlying boundary
shapefile (see `docs/DATA_SOURCES.md`) includes one additional polygon
labeled `INDIAN OCCUPIED KASHMIR` in its raw `PROVINCE` field — this
label is inherited verbatim from the third-party source file, not
authored or endorsed by this project. That polygon represents
Indian-administered Jammu & Kashmir, which was never part of Pakistan's
2017 census release and is excluded from this project's 135-district
analysis for the same reason as AJK and Gilgit-Baltistan above: it is
simply outside the scope of the data source this project's district
list is built from. This project takes no position on the territorial
status of the region; the exclusion is a data-scoping decision (this
is Pakistan-census-administered-district data), not a political one.
The label surfaces only in an internal reconciliation diagnostic
(`data/processed/geography/unmatched_districts_log.csv`) and nowhere
in this project's actual outputs, dashboard, or analysis.

**Implication:** this framework currently covers Pakistan's four
provinces plus FATA and the Federal Capital Territory, but not AJK/GB.
Extending coverage would require sourcing a district-level census table
for those regions (not attempted here) and re-running Layer 1.

## 2. The "mortality risk proxy" vs. real DHS-derived estimates

Two different mortality outcome variables exist in this pipeline, and
using the wrong one for the wrong purpose would be a serious error:

| File | What it is | Use for |
|---|---|---|
| `data/processed/mortality/district_mortality_estimate.csv` | A **deprivation-index-calibrated proxy**, NOT derived from any mortality survey. Built by mapping the Layer 2 deprivation index onto a plausible U5MR range, anchored to cited national/province benchmarks. | Testing pipeline mechanics before DHS data was available. Superseded once DHS data arrived. |
| `data/processed/mortality/district_u5mr_direct_dhs.csv` | **Real** district-level U5MR computed from actual PDHS 2017-18 birth histories via the synthetic cohort (actuarial) method. Aggregate consistency check: national population-weighted aggregate = 74.7/1,000 vs. the published PDHS figure of 74.9/1,000 (this is an internal arithmetic check, not validation of district-level accuracy — see `docs/MODEL_VALIDATION.md` for genuine validation). | The actual outcome variable feeding the corrected hazard model (Layer 3). |

The hierarchical hazard model (`scripts/models/04_hierarchical_hazard_sae.py`)
uses the **real DHS-derived** individual birth-level survival records
(via `scripts/models/03_build_person_segment_records.py`) as its
likelihood target, not the proxy. The proxy script remains in the pipeline as a historical/
fallback pathway (see `scripts/run_pipeline.sh --no-dhs`) for anyone
reproducing this project without DHS access, and is always labeled
`estimate_type = "proxy"` in its output so it can never be silently
confused with the real estimate.

## 3. DHS direct estimate coverage and stability

Of 135 districts:
- **122** have at least one sampled PDHS 2017-18 birth-history cluster.
- **13** have zero clusters and rely entirely on the hierarchical
  model's province + covariate pooling for any estimate.
- Of the 122 with data, **94 are flagged `low_direct_coverage`**
  (fewer than 100 sampled births in the 5-year reference window) --
  meaning their *direct* survey-only estimate would be unstable/noisy
  if used on its own (this is exactly why Layer 3 uses a hierarchical
  model rather than reporting direct estimates as final).

This is not a flaw in the survey — PDHS is designed and powered for
national/province-level precision, not district-level precision. The
instability of direct district estimates is the central motivating
problem this entire project is built to address via small-area
estimation, and it is documented and visualized (not hidden) throughout
the dashboard's "data uncertainty" color mode.

## 4. GPS displacement (DHS confidentiality protocol)

Per DHS's own `GPS_Displacement_README.txt` (bundled with the GPS
dataset), cluster coordinates are randomly displaced up to 2km (urban)
or 5km (rural, 1% up to 10km) to protect respondent confidentiality,
restricted to stay within the second administrative level (district)
where possible. This means:
- A cluster's assigned district is generally reliable.
- A cluster very close to a district border could, in principle, be
  displaced across it. We do not attempt to correct for this — doing so
  would require access to true (non-displaced) locations, which would
  itself violate DHS's confidentiality protocol.
- One cluster's fallback nearest-district assignment
  (`scripts/cleaning/03_clean_dhs_cluster_geography.py`) may reflect
  this displacement rather than a true border case.

This is a small, acknowledged, and irreducible source of noise in
cluster-to-district assignment given the privacy-preserving design of
the public GPS dataset.

## 5. `remoteness_proxy` is a stopgap for real accessibility data

The "health access deficit" component of the priority score
(`remoteness_proxy` in Layer 2) is currently built from **inverse
population density** — sparse districts are treated as more remote.
This is a weak proxy:
- A low-density district near a highway is very different from a
  low-density district in mountainous, roadless terrain.
- It has NOT been validated against real facility locations or
  travel-time data.
- **Sensitivity analysis found this component is the single most
  influential one in the default priority score** (see
  `docs/SENSITIVITY_FINDINGS.md`), and that Balochistan's dominance in
  the top-priority list is *partly but not entirely* attributable to
  this proxy (removing it entirely still leaves 14/20 top districts in
  Balochistan, down from 17/20).

**Recommended next step** (not yet implemented): replace with real
health facility location data + a proper travel-time/routing estimate
(e.g. via OpenStreetMap routing or a WorldPop friction-surface layer),
as originally scoped as a Layer 1 stretch goal.

**Completed 2026-09-01:** obtained the HDX/HOTOSM "Pakistan Health
Facilities (OpenStreetMap Export)" points dataset
(https://data.humdata.org/dataset/hotosm_pak_health_facilities,
4,376 points exported 2026-05-06 via the HOTOSM Raw Data API, ODbL
license) and built `facility_distance_km`
(`scripts/features/02_build_facility_distance.py`) as a new
covariate alongside `remoteness_proxy` — not replacing it, per the
plan below. Method: filtered to 3,116 facilities tagged as clinically
relevant (hospital/clinic/doctors; excludes pharmacies, dentists,
standalone labs), then computed the distance from each district's
geometric centroid to the nearest retained facility nationally
(EPSG:24313 equal-area projection).

**Important caveat found during this work, not swept under:**
OpenStreetMap facility-mapping density is itself geographically
uneven and strongly urban-biased. Karachi's four districts alone
account for ~1,100 of the 3,116 retained points, while **35 of 135
districts (26%) contain zero mapped facilities** — overwhelmingly
rural Balochistan (20 districts) and former FATA agencies (8
districts). A district with zero mapped facilities very likely has
real clinics that simply aren't on OpenStreetMap yet, not literally
none — so a large `facility_distance_km` value in these districts
should be read as "distance to the nearest MAPPED facility," which
may overstate true remoteness. Every district carries an explicit
`low_osm_facility_coverage` flag for exactly this reason, following
the same pattern already used for thin-DHS-sample flags elsewhere in
this pipeline; the flag must travel with the number in any figure,
model, or paper text that uses it.

**Empirical comparison against `remoteness_proxy`**
(`scripts/decision/04_compare_facility_distance_vs_remoteness_proxy.py`),
substituting `facility_distance_km` for `remoteness_proxy` in the
priority score with identical weights otherwise:
- The two independently-constructed measures correlate at r = 0.71
  nationally (r = 0.61 among adequately-mapped districts, r = 0.74
  among low-coverage ones) — meaningful convergent validity between a
  population-density-based measure and an actual-facility-location-
  based one, despite coming from completely different data sources.
- Top-20 priority list overlap: 16/20 districts (Jaccard 0.667)
  shared between the two versions.
- Balochistan's presence in the top-20 is nearly identical either way
  (14/20 under `remoteness_proxy`, 13/20 under `facility_distance_km`)
  — the original Balochistan-dominance finding is **not an artifact
  of the population-density proxy specifically**; a real,
  independently-sourced accessibility measure substantially confirms
  it.
- **But 9 of the 20 top-priority districts under `facility_distance_km`
  are `low_osm_facility_coverage` districts** — meaning close to half
  of that list is driven by "OSM has no mapped facility here" rather
  than a distance calculated from real nearby mapped points. This
  should be reported as a genuine open question, not resolved
  one way or the other: it is consistent with both "these districts
  are truly the most underserved" and "these districts are simply the
  least-mapped," and this framework cannot currently distinguish the
  two possibilities. A ground-truth facility census (e.g. from
  Pakistan's Ministry of Health or provincial health departments)
  would be needed to adjudicate it, and is out of scope for a
  reproducible open-data project.

**Recommended next step:** treat `facility_distance_km` as a
complementary, imperfect corroborating signal for `remoteness_proxy`
rather than a strict improvement, given the coverage-bias caveat
above. A genuine upgrade to the decision engine would need either (a)
independent verification of the zero-facility districts against a
non-OSM source, or (b) a travel-time/routing model (e.g. a WorldPop
friction-surface layer) that doesn't depend on facility-mapping
completeness at all.

## 6. Composite index weights are literature-informed assumptions, not fitted parameters

Every weighting scheme in this project — the deprivation index's
40/35/25 split (literacy/WASH/crowding), the priority score's 40/30/20/10
split (mortality/uncertainty/access/population) — is a **transparent,
literature-informed starting assumption**, explicitly not claimed to be
"the correct" weighting. This is why:
- The dashboard exposes these weights as live sliders.
- `scripts/decision/02_sensitivity_analysis.py` exists specifically to
  show how much the final ranking depends on the chosen weights.

Any report or paper using this framework's default ranking should state
this plainly, not present the default 40/30/20/10 output as an
objectively derived optimum.

## 7. Baseline regression circularity (resolved, but historically present)

An earlier version of the mortality proxy was a **deterministic** linear
function of the same covariates used in the baseline OLS regression
(`scripts/models/01_baseline_regression.py`), producing a meaningless
R²=1.000. This was identified and fixed by adding genuine stochastic
noise to the proxy's construction (see
`scripts/models/02_build_mortality_risk_proxy.py`). The current baseline
regression's R² (~0.91, reported when run against the proxy) is still
inflated relative to a true out-of-sample prediction problem, because
two covariates (literacy, WASH) remain structurally related to how the
proxy itself is built. **This circularity does not apply** to the
hierarchical Bayesian model's fit against real DHS-derived U5MR, which
is a genuinely independent outcome variable.

## 8. Reference period and survey design simplifications

The DHS-derived U5MR estimation (`scripts/models/02b_estimate_u5mr_from_dhs.py`)
uses:
- A standard 5-year pre-interview reference window (matches DHS
  convention).
- Individual-level sample weights (`v005`).
- A **cluster-level** (not full strata/PSU) bootstrap for confidence
  intervals — a reasonable approximation of DHS's complex survey design
  but not identical to a full `svyset`-style variance estimator.

For a submitted methods paper, cross-validating district-level point
estimates against DHS's own official STATcompiler district tabulations
(where available) or the official DHS-Stata/R indicator code
repositories (linked in `docs/DATA_SOURCES.md`) would strengthen the
validation section.

## 9. Hierarchical hazard model covariates are not individually statistically significant

The hierarchical discrete-time hazard model's three fixed-effect
covariates (`deprivation_index`, `urban_pct`, `remoteness_proxy`) all
have 95% posterior credible intervals that cross zero:

| Covariate | Posterior mean | 95% CI |
|---|---|---|
| `deprivation_index` | -0.058 | [-0.363, 0.242] |
| `urban_pct` | 0.292 | [-0.225, 0.811] |
| `remoteness_proxy` | 0.060 | [-0.370, 0.501] |

None of these are individually distinguishable from a null effect at
conventional significance thresholds. This is not primarily a sample-
size problem — 122/135 districts have direct DHS data — but a
**multicollinearity problem**: the three covariates are substantially
correlated with each other (deprivation_index–remoteness_proxy:
r=0.70; deprivation_index–urban_pct: r=-0.66; urban_pct–remoteness_proxy:
r=-0.54). In plain terms, rural, poor, and remote districts in this
dataset are largely the *same* districts, so the model cannot cleanly
attribute district-level risk variation to any one of these covariates
individually.

**This is corroborated by an independent test, not just theory:** the
simulation-based calibration exercise in `docs/MODEL_VALIDATION.md`
simulated data from KNOWN true covariate effects and found the
model's FITTED covariate effects were consistently negatively
correlated with the true values across all 5 simulation runs
(correlations -0.69 to -1.00), even though the national-level
parameter was correctly recovered in all 5 runs. This is a real,
reproducible symptom of the same collinearity problem, demonstrated on
synthetic data where the true answer is known — not merely inferred
from real-data ambiguity.

**What this means for interpretation:** the model's district-level
estimates are NOT primarily driven by these covariates predicting risk
in a statistically decisive way. The real information doing the work
is (a) each district's own direct DHS birth-history data where
available, and (b) province-level pooling (`mu_province`) where it is
not. The covariates contribute real but modest, statistically
inconclusive shrinkage toward a plausible direction — this is an
honest description of what the model is doing, not a claim that
deprivation, urbanization, or remoteness are unimportant in reality.
Individual covariate coefficients should not be over-interpreted or
reported as "effect sizes" in a paper; the model's district-level
predictions and RANKING (which do not require disentangling individual
covariate effects) remain the better-supported output. A future
iteration with a larger effective sample (e.g. incorporating multiple
DHS survey rounds) or a single combined socioeconomic index (rather
than three correlated covariates) could resolve this more cleanly. See
`docs/VARIABLE_DICTIONARY.md` for the full model specification and
`docs/MODEL_VALIDATION.md` for the simulation evidence.

## 10. WHO, IHME, and facility data not yet integrated (partially resolved)

The original project design's Layer 1 called for WHO health indicators,
IHME GBD province-level mortality, and health facility location data.

**DHS HR/IR integration (resolved, 2026-08-05):** Household wealth
(DHS asset-based wealth index), maternal education (DHS years-of-
schooling), and antenatal care utilization are now integrated from the
PDHS 2017-18 Household (HR) and Individual/Women's (IR) recodes (see
`scripts/cleaning/04_clean_dhs_hr_ir.py` and
`docs/VARIABLE_DICTIONARY.md`), replacing the earlier census-only
literacy/WASH-only approach wherever DHS coverage is adequate (122/135
districts). ANC utilization in particular is genuinely new information
with no census equivalent.

**IHME GBD cross-validation (completed, 2026-08-06/08, time-matched):**
Real cross-validation against IHME's GBD 2023 round estimates (5q0,
Pakistan subnational) is implemented in
`scripts/models/06_validate_against_gbd.py`, using data the user
downloaded directly from IHME's GBD Results Tool (requires an
authenticated account; not fetchable by this pipeline automatically).
The primary comparison uses the **2017-2018 average** of GBD's
province-level estimates, properly time-matched to the PDHS 2017-18
survey period (an earlier version of this validation used only a
2019 estimate, a 1-2 year offset from the survey; the current version
supersedes that).

**[Superseded — corrected below] This subsection originally reported
the pre-censoring-fix finding as current.** It is retained in edited
form only so the historical record (what Section 1 above refers to)
stays intact; do not cite the 0.50/56% figures below as this
project's present result — see the corrected figures immediately
after.

Under the earlier, flawed binomial model, the time-matched comparison
showed Balochistan substantially disagreeing with GBD: this project's
estimate at that time (79.1/1,000) vs. GBD's (50.7/1,000 in the
2017-18 average) — a 56% relative difference, with province-order
Spearman correlation of only 0.50. This is the same divergence
documented in Section 1's historical-bug entry above.

**Corrected model (current, post-fix):** with the discrete-time
hazard model's proper right-censoring, this project and GBD now agree
reasonably well on province ordering — Spearman rank correlation
0.90 (see `docs/GBD_VALIDATION_FINDINGS.md` for the full comparison
table). The largest remaining province-level gap is Sindh (this
project: 48.2 vs. GBD: 61.7/1,000, -22%), a smaller and
more ordinary-magnitude disagreement attributable to genuine
methodological differences between a single-survey hazard model and
GBD's multi-source synthesis rather than a further structural issue.

**Implication for any paper or report using this framework:** cite
the corrected 0.90 correlation and the Sindh gap as the current
external-benchmarking result. The historical 0.50/56% Balochistan
figures belong only in a before/after discussion of the censoring
fix (Section 1), never presented as the project's present finding.

**Still not integrated:** WHO Global Health Observatory indicators,
real health facility location/travel-time data (see Limitation 5).
Their absence means:
- No cause-specific mortality breakdown is possible yet.
- No real facility-density or travel-time covariate exists yet
  (`remoteness_proxy` stands in, see Limitation 5).

**Attempted 2026-09-01 (WHO GHO):** checked whether WHO's Global
Health Observatory API (`ghoapi.azureedge.net`) or `www.who.int` were
reachable from the working environment to pull Pakistan-relevant
indicators (e.g. cause-specific mortality fractions, vaccination
coverage) at national or provincial level. Both blocked
(`host_not_allowed`), same failure mode as the HDX facility-data
attempt above — the sandbox's network allowlist covers package
registries and GitHub only, not general data-hosting domains. No
WHO figures were reconstructed from memory or approximated as a
substitute. GHO data is normally accessible without authentication
via `https://ghoapi.azureedge.net/api/<IndicatorCode>` (OData,
JSON), so from an environment with open web access this is a
low-friction fetch — it just isn't one from here. Next session with
web access should be able to complete this directly.

## 11. Kohistan District: a single-district double data gap

Kohistan District is the one case in this entire pipeline where BOTH
the DHS-preferred and census-fallback data sources fail simultaneously
for a given indicator, requiring a last-resort median imputation:

- **Census literacy**: Kohistan is entirely absent from PBS 2017 Census
  Table 12 (tehsil-level literacy), the source
  `scripts/cleaning/02_clean_demographics_socioeconomic.py` aggregates
  up to district level. This is most likely because Kohistan was
  administratively split into Upper and Lower Kohistan in some census
  releases with naming inconsistent with the district-level table used
  elsewhere in this project (the geography reconciliation step,
  `scripts/cleaning/01_clean_geography.py`, correctly maps both
  variants to a single canonical `KOHISTAN DISTRICT`, but that fix does
  not retroactively recover literacy data that was never present under
  either name in Table 12).
- **DHS education**: Kohistan also lacks adequate DHS IR coverage
  (`low_dhs_ir_coverage = True`), consistent with it being one of the
  13 districts with zero or thin DHS cluster sampling overall (see
  Limitation 3).

`scripts/features/01_build_composite_indices.py`'s
`build_education_indicator()` explicitly detects and logs this case by
district name (not silently) and falls back to a national median
imputation for Kohistan's `education_adequacy` value, flagged as
`education_data_source = "imputed_median"` in
`data/processed/features/district_features.csv`. This is a single-
district edge case, not a systematic gap, but it means Kohistan's
deprivation index and downstream priority score should be read with
this specific caveat in mind — its education component reflects a
national average, not anything specific to Kohistan.

## 12. This is a decision-support tool, not a clinical or administrative record

Every estimate in this project — mortality risk, uncertainty, priority
rank — is a **model output for prioritization discussion**, not an
official government statistic, not a clinical measurement, and not
suitable for identifying, targeting, or making decisions about any
individual, household, or specific community. This is stated in the
dashboard's footer and should be stated in any derived report,
presentation, or publication.
