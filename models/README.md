# Models

Saved fitted model artifacts, committed to the repo for reproducibility.

- `baseline_regression_model.pkl` (32KB) -- fitted statsmodels OLS object
  from `scripts/models/01_baseline_regression.py`
- `hierarchical_hazard_sae_trace.pkl` (~58MB) -- full PyMC posterior
  trace (InferenceData object, pickled) from the corrected discrete-
  time hazard model, `scripts/models/04_hierarchical_hazard_sae.py`.
  Kept so anyone can re-run convergence diagnostics (R-hat, ESS, trace
  plots), posterior predictive checks, or ranking stability analysis
  (`scripts/decision/03_ranking_stability.py`) without re-running MCMC
  sampling. This is under GitHub's 100MB hard file-size limit but above
  the 50MB soft-warning threshold -- if cloning becomes slow, consider
  Git LFS for this file.

**Note:** the trace from the earlier, deprecated binomial-likelihood
model (`scripts/models/03_DEPRECATED_hierarchical_bayesian_sae_binomial.py`)
has been removed from this directory. That script's real methodological
flaw (incorrect right-censoring handling) and its concrete before/after
impact are documented in full in `docs/LIMITATIONS.md` and
`docs/GBD_VALIDATION_FINDINGS.md` -- the deprecated script itself is
kept (clearly marked, and excluded from `scripts/run_pipeline.sh`) as a
historical record, but its multi-megabyte trace added bulk without
adding evidentiary value beyond what's already documented in text.

Load the trace with:
```python
import pickle
with open("models/hierarchical_hazard_sae_trace.pkl", "rb") as f:
    trace = pickle.load(f)
```
