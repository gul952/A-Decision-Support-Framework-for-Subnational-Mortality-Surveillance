# Variable Dictionary

Every variable produced by this pipeline, its source, and the
transformation applied to create it. Organized by output file, in
pipeline order. See `docs/DATA_SOURCES.md` for full source citations
and `docs/LIMITATIONS.md` for caveats on specific variables.

---

## `data/processed/geography/districts.geojson` / `district_master_key.csv`
*Produced by `scripts/cleaning/01_clean_geography.py`*

| Variable | Description | Source | Transformation |
|---|---|---|---|
| `district_key` | Canonical district identifier, format `"<NAME> DISTRICT"`, upper case | Derived | Standardized from both PBS census names and shapefile `DISTRICT` field; abbreviation/spelling divergences (e.g. "D.G. Khan" → "Dera Ghazi Khan") reconciled via explicit crosswalk in code |
| `province` | Province/region name | PBS census shapefile `PROVINCE` field | Title-cased |
| `area_sqkm` | District land area, km² | PBS 2017 Census, Table 01 | Direct |
| `census_population_2017` | Total population, 2017 census | PBS 2017 Census, Table 01 | Direct |
| `geometry` | District boundary polygon | PBS census shapefile (OCHA-sourced boundaries) | Dissolved to one polygon per canonical district, invalid geometries repaired via `buffer(0)` |

---

## `data/processed/demographics/district_demographics_socioeconomic.csv`
*Produced by `scripts/cleaning/02_clean_demographics_socioeconomic.py`*

| Variable | Description | Source | Transformation |
|---|---|---|---|
| `population_2017` | Total population | PBS Census Table 01 | Direct |
| `male`, `female` | Population by sex | PBS Census Table 01 | Direct |
| `sex_ratio` | Males per 100 females | PBS Census Table 01 | Direct |
| `pop_density_per_sqkm` | Population density | PBS Census Table 01 | Direct |
| `urban_pct` | % population in census-designated urban localities | PBS Census Table 01 | Districts with zero designated urban localities (mostly former FATA agencies) imputed to 0%, not left null — see code comments in the cleaning script |
| `avg_household_size` | Mean persons per household | PBS Census Table 01 | Direct |
| `pop_growth_rate_pct` | Average annual population growth, 1998–2017 | PBS Census Table 01 | Direct |
| `population_under5` | Population aged 0–4 | PBS Census Table 08 (age-disaggregated) | Summed across rural/urban locale and sex for the "00 - 04" age band |
| `literacy_rate_pct` | % population literate | PBS Census Table 12 | Only available at tehsil level in the source; aggregated to district by summing `total_pop` and `literate_total` across all tehsils/locales/sexes/ages, THEN recomputing the ratio (a proper weighted aggregation, not an average of pre-computed tehsil ratios) |
| `mean_persons_per_room` | Household crowding indicator | PBS Census Table 29 | Household-size category (e.g. "10 PERSONS AND ABOVE") midpoint-decoded, divided by rooms-in-house category, weighted by household count |
| `improved_water_pct` | % households with piped/hand-pump water inside the home | PBS Census Table 35 | "Improved" = Tap or Electric/Hand Pump, located Inside the home (WHO/UNICEF JMP-style simplification) |
| `improved_sanitation_pct` | % households with sewerage- or septic-connected latrine | PBS Census Table 37 | "Improved" = Connected With Sewerage or Connected With Septic Tank |

---

## `data/processed/features/district_features.csv`
*Produced by `scripts/features/01_build_composite_indices.py`*

All variables above, plus:

| Variable | Description | Formula | Weighting rationale |
|---|---|---|---|
| `*_imputed` (multiple) | Boolean flag, true if the paired column was median-imputed | — | Traceability: every imputation is flagged, never silent |
| `wash_index` | Water/Sanitation/Hygiene composite, higher = better | `0.5 × norm(improved_water_pct) + 0.5 × norm(improved_sanitation_pct)` | Equal-weighted; both are standard WHO/UNICEF JMP "improved" indicators |
| `household_pressure_index` | Crowding composite, higher = more pressure | `0.5 × norm(mean_persons_per_room) + 0.5 × norm(avg_household_size)` | Equal-weighted |
| `remoteness_proxy` | Physical accessibility STOPGAP, higher = more remote | `1 − norm(log(1 + pop_density_per_sqkm))` | **Weak proxy** — see `docs/LIMITATIONS.md` §5. Not validated against real travel-time/facility data. |
| `facility_distance_km` | Distance from district centroid to nearest mapped health facility, km | Haversine-equivalent planar distance (EPSG:24313) to nearest OSM-mapped hospital/clinic/doctor nationally | Real geolocated facility data, added alongside `remoteness_proxy` for comparison — see `docs/LIMITATIONS.md` §5. **Caveat: OSM facility-mapping coverage is itself uneven; see `low_osm_facility_coverage`.** |
| `facility_count_in_district` | Count of clinically-relevant OSM facilities within the district polygon | Spatial join, `scripts/features/02_build_facility_distance.py` | Diagnostic only — not area- or population-adjusted, not used directly in the priority score |
| `low_osm_facility_coverage` | Boolean flag, true if `facility_count_in_district == 0` | Derived | 35/135 districts (26%) — flags where `facility_distance_km` reflects "distance to nearest MAPPED facility," not necessarily true remoteness, since these districts may have real unmapped clinics. Must accompany `facility_distance_km` wherever it's used, per `docs/LIMITATIONS.md` §5. |
| `under5_share_pct` | % of district population under 5 | `100 × population_under5 / population_2017` | Demographic exposure indicator, used in decision engine's population weighting |
| `deprivation_index` | Composite socioeconomic deprivation, higher = more deprived | `0.40 × (1 − norm(literacy_rate_pct)) + 0.35 × (1 − wash_index) + 0.25 × household_pressure_index` | Literature-informed (not fitted): education is the strongest established socioeconomic predictor of child mortality in LMIC DHS studies (40%); WASH has a direct causal pathway to diarrheal disease and child mortality (35%); crowding relates to infectious disease transmission (25%) |

**SUPERSEDED as of DHS HR/IR integration — see the updated section below.**
The row above describes the original census-only version of this index.

---

## `data/processed/dhs_derived/district_dhs_socioeconomic.csv`
*Produced by `scripts/cleaning/04_clean_dhs_hr_ir.py`*

DHS Household (HR) and Individual/Women's (IR) recode indicators,
aggregated to district level. These are the richer, individual-level
DHS measures that REPLACE the census-only literacy/WASH proxies in
Layer 2 wherever DHS coverage is adequate (see `deprivation_data_source`
below).

| Variable | Description | Source variable | Transformation |
|---|---|---|---|
| `n_households_hr` | Sampled households in this district | PDHS HR file, `hv001` × cluster-district lookup | Count |
| `mean_wealth_score` | Weighted mean DHS wealth index factor score | PDHS HR `hv271` | DHS standard rescale (`/100,000`), weighted by `hv005/1,000,000` |
| `pct_lowest_wealth_quintile` | % of households in the poorest national wealth quintile | PDHS HR `hv270` | Weighted % where `hv270 == 1` |
| `n_women_ir` | Sampled women in this district | PDHS IR file, `v001` × cluster-district lookup | Count |
| `mean_years_education` | Weighted mean years of schooling | PDHS IR `v133` ("education in single years", DHS's own pre-combined variable) | Weighted by `v005/1,000,000` |
| `pct_no_education` | % of women with no formal education | PDHS IR `v106` | Weighted % where `v106 == 0` |
| `mean_anc_visits` | Weighted mean antenatal care visits (most recent birth, 5yr window) | PDHS IR `m14_1` | DHS "don't know" code (98) excluded; weighted by `v005/1,000,000` |
| `pct_zero_anc_visits` | % of recent births with zero ANC visits | PDHS IR `m14_1` | Weighted % where visits == 0 |
| `low_dhs_hr_coverage` / `low_dhs_ir_coverage` / `low_dhs_anc_coverage` | Boolean flags | Derived | True if underlying sample size < 30 records — the threshold below which a district-level DHS mean is considered unstable |

**Why this matters:** the DHS wealth index (`hv271`) is a continuous,
asset-based PCA measure — the standard socioeconomic indicator used
throughout the global child-mortality literature — genuinely richer
than the census's binary "improved water: yes/no." `mean_anc_visits`
has **no census equivalent at all**: it is new information about
health-service utilization that only exists because DHS individual-
level data was integrated.

**Validation:** the wealth score's geographic pattern passes an
external validity check — Karachi East/Central, Lahore, and Islamabad
rank as wealthiest; Tharparkar and Rajanpur (both well-documented in
the development literature as among Pakistan's poorest districts) rank
lowest.

---

## `data/processed/dhs_derived/district_vaccination_coverage.csv` → merged into `district_features.csv`
*Produced by `scripts/cleaning/05_clean_dhs_kr_vaccination.py`*

DHS Children's Recode (KR) vaccination indicators, aggregated to
district level, then merged into the published `district_features.csv`
via `scripts/features/01_build_composite_indices.py` — same
compliance pattern as `district_dhs_socioeconomic.csv` above (the
standalone file stays in the gitignored `dhs_derived/` directory since
it is a DHS-derived compliance-boundary intermediate, but its
district-aggregated, non-identifying values ARE published downstream,
per `docs/DATA_SOURCES.md`'s compliance notes). Added as a second,
independent external validation axis for the mortality model — see
`docs/LIMITATIONS.md` §10a for full method and findings (including an
honest null/mixed district-level result, attributed to small
district-level sample sizes).

| Variable | Description | Source variable | Transformation |
|---|---|---|---|
| `n_children_12_23mo` | Sampled children aged 12-23 months, alive at interview | PDHS KR `b5`, `b19` | Standard international reference cohort for vaccination-coverage reporting |
| `pct_fully_vaccinated` | % receiving BCG + Pentavalent(1-3) + Polio(1-3) + Measles(1) | PDHS KR `h2,h51,h52,h53,h4,h6,h8,h9` | DHS standard "received" codes {1,2,3} (card date / mother-reported / marked without date); weighted by `v005/1,000,000` |
| `pct_zero_dose` | % receiving none of the 8 above | Same source variables | Weighted, as above |
| `pct_bcg` / `pct_measles1` / `pct_penta3` | Individual-antigen coverage | `h2` / `h9` / `h53` respectively | Weighted, as above |
| `low_vaccination_sample` | Boolean flag | Derived | True if `n_children_12_23mo < 25` — 100/119 districts with any data are flagged; the district-level composite is expected to be noisy at typical district sample sizes (median n=13) |

**Validation:** national aggregate (65.6% fully vaccinated) matches
the PDHS 2017-18's own published national figure (65.6%) exactly;
Punjab's provincial rate (79.9%) closely matches its published figure
(80.3%). Balochistan's provincial rate diverged more from a published
comparison figure (28.8% vs. ~40%) — reported as an open,
unresolved discrepancy, not adjusted to match.

---

## `data/processed/features/district_features.csv` — updated deprivation index
*Produced by `scripts/features/01_build_composite_indices.py`*

The current (post-DHS-integration) version of the composite indices:

| Variable | Description | Formula | Data source logic |
|---|---|---|---|
| `education_adequacy` | Normalized [0,1] education indicator, higher = better | DHS: `norm(mean_years_education)`; Census fallback: `norm(literacy_rate_pct)` | DHS used where `mean_years_education` is non-null AND `low_dhs_ir_coverage` is False (≥30 sampled women); census fallback otherwise |
| `education_data_source` | `"dhs"`, `"census"`, or `"imputed_median"` | — | Traceability flag |
| `wealth_adequacy` | Normalized [0,1] wealth indicator, higher = wealthier | DHS: `norm(mean_wealth_score)`; Census fallback: `wash_index` (as a rough proxy) | DHS used where `mean_wealth_score` is non-null AND `low_dhs_hr_coverage` is False |
| `wealth_data_source` | `"dhs"` or `"census_wash_proxy"` | — | Traceability flag |
| `anc_deficit_index` | Antenatal care under-utilization, higher = more deficit | `1 - norm(mean_anc_visits)` where DHS ANC coverage adequate; else median-imputed | **No census fallback exists** — this is new information only, imputed (and flagged) where DHS coverage is thin |
| `anc_data_source` | `"dhs"`, `"imputed_median"` | — | Traceability flag |
| `deprivation_index` (current) | Composite socioeconomic deprivation, higher = more deprived | `0.35 × (1 − education_adequacy) + 0.30 × (1 − wealth_adequacy) + 0.20 × (1 − wash_index) + 0.15 × household_pressure_index` | Weights updated from the original literacy/WASH/crowding-only version to reflect the richer education + wealth split |
| `deprivation_data_source` | e.g. `"education=dhs;wealth=dhs"` | — | Per-district traceability of exactly which inputs (DHS vs. census) fed the composite score — DHS used wherever reliable, census remains an honest, flagged fallback |

**Coverage:** 122/135 districts use DHS-derived education; 122/135 use
DHS-derived wealth; the remaining 12-13 fall back to census, all
explicitly flagged via `*_data_source`, never silently blended.

---

## `data/processed/mortality/district_mortality_estimate.csv` — **PROXY, not real data**
*Produced by `scripts/models/02_build_mortality_risk_proxy.py`*

See `docs/LIMITATIONS.md` §2 before using this file. Superseded by the
DHS-derived file below wherever DHS coverage exists.

| Variable | Description | Transformation |
|---|---|---|
| `mortality_estimate_per1000` | Calibrated proxy U5MR | Linear map of `deprivation_index` onto [45, 130] per-1,000 range, re-centered so the population-weighted mean equals the cited national U5MR (74.9/1,000, World Bank/UN IGME 2017), plus Gaussian noise (SD = 8% of anchor range) so it is not perfectly collinear with its own inputs |
| `mortality_lower95` / `mortality_upper95` | Proxy uncertainty band | ± 35% of point estimate (a modeling choice, not a measured sampling error) |
| `estimate_type` | Always `"proxy"` | Literal tag so this can never be mistaken for a real estimate downstream |

---

## `data/processed/dhs_derived/` — DHS-derived, compliance-boundary outputs
*Produced by `scripts/cleaning/03_clean_dhs_cluster_geography.py`*

| File | Variable | Description | Compliance note |
|---|---|---|---|
| `cluster_district_lookup.csv` | `DHSCLUST` → `district_key` | Cluster-to-district spatial join result | Cluster IDs are a survey design index, not a respondent identifier; safe as a derived artifact but not published verbatim in the dashboard |
| `district_cluster_counts.csv` | `n_clusters_total`, `n_clusters_urban`, `n_clusters_rural` | Count of DHS clusters per district | Aggregate only; this is the coverage diagnostic motivating the SAE approach |

---

## `data/processed/mortality/district_u5mr_direct_dhs.csv` — **Real DHS-derived estimate (public-safe subset)**
*Produced by `scripts/models/02b_estimate_u5mr_from_dhs.py`*

**Two-tier output (see `docs/COMPLIANCE.md` "Small-cell policy"):** this
script writes a full version with raw counts to the gitignored
`data/processed/dhs_derived/district_u5mr_direct_dhs_full.csv` (used
internally by `03_build_person_segment_records.py` and
`07_model_validation.py`), and a public-safe subset — documented below
— to this committed path. The raw `n_births_5yr`/`n_deaths_u5_5yr`/
`n_clusters` columns are **not** in the committed file; some districts
have as few as 1 sampled cluster or 0 recorded deaths, and publishing
those exact counts next to a named district was judged a small-cell
disclosure risk. This is a conservative repository policy choice, not
a claim that DHS's terms mandate this specific suppression.

| Variable | Description | Source | Transformation |
|---|---|---|---|
| `u5mr_direct` | Direct (design-based) U5MR estimate, per 1,000 live births | PDHS 2017-18 BR file | Synthetic cohort (actuarial) life table method: chained segment-specific survival probabilities across 8 standard age segments (0, 1-2, 3-5, 6-11, 12-23, 24-35, 36-47, 48-59 months), with **actuarial (person-time) exposure correction** for children too young at interview to have completed a segment (a real bug found and fixed during development — see `docs/LIMITATIONS.md` §7 for the historical binary-censoring version that produced unstable 1000/1000 estimates in thin segments). Weighted using DHS sample weights (`v005 / 1,000,000`). |
| `u5mr_lower95` / `u5mr_upper95` | 95% CI on the direct estimate | PDHS 2017-18 BR file | Cluster-aware (not individual-level) bootstrap, 300 resamples, respecting DHS's clustered survey design |
| `low_direct_coverage` | Boolean flag | Derived | True if `n_births_5yr < 100` (see full file) — a rule-of-thumb threshold below which the direct estimate alone is considered unstable |
| `estimate_type` | Always `"dhs_direct"` | — | — |

The full (local-only) file additionally has `n_births_5yr`,
`n_deaths_u5_5yr` (Under-5 deaths among those births; PDHS `b5`/`b7`),
and `n_clusters` (distinct DHS clusters sampled, via `v001` × the GPS
cluster-district lookup) — see the script's docstring for exact
definitions.

**Validation:** the population-weighted national aggregate of this
method = 74.7 deaths/1,000 live births, vs. the published PDHS 2017-18
national U5MR of 74.9/1,000 (World Bank/UN IGME) — a 0.2-point
difference, confirming the reimplementation is methodologically sound.

---

## `data/processed/models/hierarchical_hazard_sae_results.csv`
*Produced by `scripts/models/04_hierarchical_hazard_sae.py`*

**[Corrected 2026-09-01 — this section previously described the
deprecated binomial model's structure and the wrong output filename.
The active model is the discrete-time hazard model below; the earlier
`03_DEPRECATED_hierarchical_bayesian_sae_binomial.py` is retained only
as a documented before/after record, is not called by
`scripts/run_pipeline.sh`, and should not be cited as the project's
current method — see `docs/LIMITATIONS.md` §1 and
`docs/GBD_VALIDATION_FINDINGS.md`.]**

| Variable | Description | Model component |
|---|---|---|
| `had_direct_data` | Whether this district had ≥1 sampled DHS birth | — |
| `n_births_direct` | Same as `n_births_5yr` above | — |
| `u5mr_posterior_mean` | Posterior mean U5MR estimate, per 1,000 | Bayesian hierarchical discrete-time hazard model — see below |
| `u5mr_ci_lower95` / `u5mr_ci_upper95` | 95% posterior credible interval | 2.5th/97.5th percentile of the posterior segment-probability samples, chained via the actuarial formula below |
| `ci_width` | `u5mr_ci_upper95 − u5mr_ci_lower95` | Used directly as the "uncertainty" component in the priority score |
| `run_mode` | `"normal"` or `"no_dhs_prior_only"` | Traceability flag: `"no_dhs_prior_only"` means the entire model ran with zero DHS data anywhere (all 135 districts `had_direct_data=False`) -- a degenerate fallback mode that exists only so `scripts/run_pipeline.sh --no-dhs` doesn't crash for a reader without DHS access. Results under this mode reflect only the model's prior, not survey evidence, and are explicitly NOT a usable mortality estimate -- see `docs/LIMITATIONS.md`. Guarded by a refuse-to-overwrite safeguard requiring `--force-no-dhs` if a real (`"normal"`) result already exists, to prevent accidentally clobbering a genuine analysis. |
| `model_version` | Always `"hazard_v1_censoring_corrected"` | Literal tag distinguishing this output from any legacy binomial-model artifact |

**Model structure** (discrete-time hazard / Poisson person-time model,
fit on person-segment survival records, logit link on the per-segment
hazard):
```
For each (district d, age segment s) cell:
    weighted_events_ds ~ Poisson(p_ds * weighted_exposure_ds)
    logit(p_ds) = alpha_segment[s] + mu_province[province_d]
                  + beta . X_d + eps_district_d

    p_ds = probability of death WITHIN segment s, for a child who
           entered the segment alive (a discrete-time hazard on the
           segment scale, not an instantaneous per-month rate)

    alpha_segment[s] ~ Normal(0, 2)      [8 standard DHS age segments:
                                           0, 1-2, 3-5, 6-11, 12-23,
                                           24-35, 36-47, 48-59 months]
    mu_province[p] ~ Normal(mu_national, sigma_province)
    mu_national ~ Normal(0, 1)
    beta ~ Normal(0, 1)     [covariates: deprivation_index, urban_pct,
                              remoteness_proxy, all standardized]
    sigma_province, sigma_district ~ HalfNormal(1)
```
Fit via PyMC (NUTS sampler, 4 chains × 1500 draws, target_accept=0.95).
Convergence: R-hat = 1.000 across all parameters, no divergences (see
console output logged during the pipeline run).

District-level U5MR is reconstructed from the fitted segment death
probabilities via the same actuarial chaining formula used in the
direct estimator — `U5MR = 1 - PROD_segments(1 - p_s)` — computed from
POSTERIOR SAMPLES of the segment probabilities, so the reported 95%
credible interval correctly propagates all model uncertainty rather
than reflecting only a single aggregate rate's uncertainty.

This replaces an earlier model that fit
`deaths_d ~ Binomial(n_births_d, p_d)` directly on already-aggregated
district counts, which implicitly assumed every child had a full,
uncensored 5-year follow-up window — incorrect, since children born
recently before the interview had only been at risk for a few months.
See `docs/LIMITATIONS.md` §1 for the concrete evidence (Balochistan
GBD-divergence before/after) that this correction materially changed
results, not just theoretical correctness.

Districts with `had_direct_data = False` contribute no likelihood term
(PyMC handles zero-exposure cells as a zero log-likelihood contribution
automatically) — their posterior is driven entirely by
`mu_province` + `beta · X` + segment baseline hazard, which is the
small-area "borrowing strength" mechanism this model exists to provide.

---

## `data/processed/decision/district_priority_scores.csv`
*Produced by `scripts/decision/01_prioritization_engine.py`*

| Variable | Description | Formula |
|---|---|---|
| `norm_mortality_risk` | Min-max normalized `u5mr_posterior_mean`, [0,1] | `(x - min) / (max - min)` |
| `norm_uncertainty` | Min-max normalized `ci_width` | Same |
| `norm_geographic_accessibility_proxy` | Min-max normalized `remoteness_proxy` -- a population-density-based geographic accessibility PROXY, NOT actual healthcare access (no real facility/travel-time data used; see docs/LIMITATIONS.md) | Same |
| `norm_population` | Min-max normalized `population_2017` | Same |
| `priority_score` | Composite prioritization score, [0,1] | `0.40 × norm_mortality_risk + 0.30 × norm_uncertainty + 0.20 × norm_geographic_accessibility_proxy + 0.10 × norm_population` (default weights; adjustable — see `docs/LIMITATIONS.md` and the dashboard's live sliders) |
| `rank` | District rank by `priority_score`, descending | `rank(priority_score, method="min")` |

---

## `data/processed/decision/sensitivity_*.csv`
*Produced by `scripts/decision/02_sensitivity_analysis.py`*

See `docs/SENSITIVITY_FINDINGS.md` for the full narrative interpretation
of these files, including the Balochistan-dominance robustness check.
