import React, { useState, useMemo, useCallback } from 'react';
import { DISTRICTS_DATA } from './districtsData';


// ---------------------------------------------------------------------
// Pakistan Subnational Mortality Surveillance -- Decision Support Dashboard
// ---------------------------------------------------------------------
// Design: clinical / data-forward. Deep slate canvas, amber-to-coral risk
// ramp (avoids red/green colorblind ambiguity and "alarm" framing of pure
// red), monospace numerals for measured quantities. The map is the hero;
// everything else supports "why is this district ranked here."
//
// DATA PROVENANCE (surfaced in-app, not just in code comments):
//   - Geography: PBS 2017 Census district boundaries (135 districts)
//   - Mortality (u5mr): Bayesian hierarchical discrete-time hazard model
//     with proper right-censoring, built on
//     REAL PDHS 2017-18 birth-history direct estimates where available
//     (122/135 districts have direct DHS data; 13 rely purely on
//     province+covariate pooling). NOT official government statistics --
//     modeled estimates for decision support only.
//   - Deprivation/access/literacy/WASH: PBS 2017 Census + composite
//     indices (Layer 2 feature engineering).

function minmax(arr) {
  const min = Math.min(...arr);
  const max = Math.max(...arr);
  const range = max - min;
  return arr.map((v) => (range === 0 ? 0.5 : (v - min) / range));
}

function computeScores(features, weights) {
  const mort = features.map((f) => f.u5mr);
  const unc = features.map((f) => f.ci_w);
  const acc = features.map((f) => f.access);
  const pop = features.map((f) => f.pop);

  const nMort = minmax(mort);
  const nUnc = minmax(unc);
  const nAcc = minmax(acc);
  const nPop = minmax(pop);

  const scored = features.map((f, i) => ({
    ...f,
    normMort: nMort[i],
    normUnc: nUnc[i],
    normAcc: nAcc[i],
    normPop: nPop[i],
    score:
      weights.mortality * nMort[i] +
      weights.uncertainty * nUnc[i] +
      weights.access * nAcc[i] +
      weights.population * nPop[i],
  }));

  scored.sort((a, b) => b.score - a.score);
  scored.forEach((d, i) => {
    d.rank = i + 1;
  });
  return scored;
}

// Project lon/lat to simple equirectangular screen coords for Pakistan's
// bounding box -- adequate for a choropleth at this scale (no need for a
// heavier projection library for a single-country static extent map).
const BOUNDS = { lonMin: 60.8, lonMax: 77.9, latMin: 23.5, latMax: 37.1 };
const VIEW_W = 640;
const VIEW_H = 620;

function project([lon, lat]) {
  const x = ((lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * VIEW_W;
  const y = VIEW_H - ((lat - BOUNDS.latMin) / (BOUNDS.latMax - BOUNDS.latMin)) * VIEW_H;
  return [x, y];
}

function ringToPath(ring) {
  return ring
    .map(([lon, lat], i) => {
      const [x, y] = project([lon, lat]);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ') + 'Z';
}

function geomToPath(geom) {
  if (geom.type === 'Polygon') {
    return geom.coordinates.map(ringToPath).join(' ');
  }
  if (geom.type === 'MultiPolygon') {
    return geom.coordinates.map((poly) => poly.map(ringToPath).join(' ')).join(' ');
  }
  return '';
}

// Amber (low risk) -> coral/red (high risk) ramp, colorblind-safer than
// red/green and doesn't read as "danger vs safe" the way traffic-light
// colors do -- appropriate since even "low" districts here are modeled
// estimates with real uncertainty, not a clean bill of health.
function riskColor(normValue) {
  const stops = [
    [0.0, [250, 238, 218]],   // pale amber
    [0.35, [250, 199, 117]],  // amber
    [0.6, [239, 159, 39]],    // deep amber
    [0.8, [216, 90, 48]],     // coral
    [1.0, [153, 60, 29]],     // deep coral/rust
  ];
  let lo = stops[0], hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (normValue >= stops[i][0] && normValue <= stops[i + 1][0]) {
      lo = stops[i]; hi = stops[i + 1]; break;
    }
  }
  const range = hi[0] - lo[0];
  const t = range === 0 ? 0 : (normValue - lo[0]) / range;
  const rgb = lo[1].map((c, i) => Math.round(c + t * (hi[1][i] - c)));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function fmt(n, decimals = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return Number(n).toFixed(decimals);
}

function fmtInt(n) {
  if (n === null || n === undefined) return '—';
  return Math.round(n).toLocaleString();
}

const DEFAULT_WEIGHTS = { mortality: 0.4, uncertainty: 0.3, access: 0.2, population: 0.1 };

const WEIGHT_LABELS = {
  mortality: 'Mortality risk',
  uncertainty: 'Data uncertainty',
  access: 'Geographic accessibility proxy',
  population: 'Population',
};

const WEIGHT_COLORS = {
  mortality: '#D85A30',
  uncertainty: '#7F77DD',
  access: '#5DCAA5',
  population: '#85B7EB',
};

export default function MortalitySurveillanceDashboard() {
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [selectedKey, setSelectedKey] = useState(null);
  const [hoveredKey, setHoveredKey] = useState(null);
  const [colorMode, setColorMode] = useState('score'); // 'score' | 'u5mr' | 'uncertainty'
  const [budgetN, setBudgetN] = useState(20);

  const features = DISTRICTS_DATA.features;

  const scored = useMemo(() => computeScores(features, weights), [features, weights]);
  const scoredByKey = useMemo(() => {
    const m = {};
    scored.forEach((d) => { m[d.k] = d; });
    return m;
  }, [scored]);

  const topN = useMemo(() => scored.slice(0, budgetN), [scored, budgetN]);
  const topNKeys = useMemo(() => new Set(topN.map((d) => d.k)), [topN]);

  const selected = selectedKey ? scoredByKey[selectedKey] : null;
  const hovered = hoveredKey ? scoredByKey[hoveredKey] : null;
  const displayed = selected || hovered;

  const handleWeightChange = useCallback((key, value) => {
    setWeights((prev) => {
      const next = { ...prev, [key]: value };
      const total = Object.values(next).reduce((a, b) => a + b, 0);
      if (total === 0) return prev;
      // renormalize so weights always sum to 1
      const normalized = {};
      Object.keys(next).forEach((k) => { normalized[k] = next[k] / total; });
      return normalized;
    });
  }, []);

  const resetWeights = () => setWeights(DEFAULT_WEIGHTS);

  const colorFor = (d) => {
    if (colorMode === 'u5mr') return riskColor(d.normMort);
    if (colorMode === 'uncertainty') return riskColor(d.normUnc);
    return riskColor(d.score);
  };

  return (
    <div style={{
      background: '#12181f',
      color: '#e8e6e0',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      minHeight: '100vh',
      padding: '0',
    }}>
      {/* Header */}
      <div style={{
        borderBottom: '1px solid #2a323c',
        padding: '20px 28px 18px',
        background: '#161d25',
      }}>
        <div style={{ fontSize: 11, letterSpacing: '0.08em', color: '#8a95a3', textTransform: 'uppercase', marginBottom: 6 }}>
          Decision-support framework · not official statistics
        </div>
        <h1 style={{ fontSize: 21, fontWeight: 600, margin: 0, color: '#f5f3ee' }}>
          Subnational mortality surveillance prioritization — Pakistan
        </h1>
        <div style={{ fontSize: 13, color: '#8a95a3', marginTop: 5, maxWidth: 720, lineHeight: 1.5 }}>
          Modeled under-5 mortality risk (Bayesian hierarchical discrete-time hazard model, built on PDHS 2017-18 birth histories where available) combined with data uncertainty, a population-density-based geographic accessibility proxy (not actual healthcare access), and population into a transparent district prioritization score.
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 0 }}>
        {/* Left: Map + controls */}
        <div style={{ flex: '1 1 640px', padding: '20px 24px', minWidth: 480 }}>

          {/* Color mode + budget controls */}
          <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 6 }}>
              {[
                ['score', 'Priority score'],
                ['u5mr', 'Mortality risk'],
                ['uncertainty', 'Data uncertainty'],
              ].map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => setColorMode(mode)}
                  style={{
                    fontSize: 12,
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: `1px solid ${colorMode === mode ? '#d97757' : '#2a323c'}`,
                    background: colorMode === mode ? 'rgba(217,119,87,0.15)' : 'transparent',
                    color: colorMode === mode ? '#e8956f' : '#8a95a3',
                    cursor: 'pointer',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#8a95a3' }}>
              <span>Top-N budget:</span>
              {[5, 10, 20, 50].map((n) => (
                <button
                  key={n}
                  onClick={() => setBudgetN(n)}
                  style={{
                    fontSize: 12,
                    padding: '4px 10px',
                    borderRadius: 6,
                    border: `1px solid ${budgetN === n ? '#5dcaa5' : '#2a323c'}`,
                    background: budgetN === n ? 'rgba(93,202,165,0.12)' : 'transparent',
                    color: budgetN === n ? '#7fd9b8' : '#8a95a3',
                    cursor: 'pointer',
                  }}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Map */}
          <div style={{ background: '#0d1218', borderRadius: 10, border: '1px solid #232b34', padding: 12 }}>
            <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
              {scored.map((d) => {
                const path = geomToPath(d.geom);
                const isTopN = topNKeys.has(d.k);
                const isSelected = selectedKey === d.k;
                const isHovered = hoveredKey === d.k;
                return (
                  <path
                    key={d.k}
                    d={path}
                    fill={colorFor(d)}
                    stroke={isSelected ? '#f5f3ee' : isTopN ? '#f5f3ee' : '#0d1218'}
                    strokeWidth={isSelected ? 2 : isTopN ? 1 : 0.4}
                    strokeOpacity={isSelected ? 1 : isTopN ? 0.55 : 0.5}
                    style={{ cursor: 'pointer', transition: 'opacity 0.1s' }}
                    opacity={isHovered || isSelected ? 1 : 0.92}
                    onMouseEnter={() => setHoveredKey(d.k)}
                    onMouseLeave={() => setHoveredKey(null)}
                    onClick={() => setSelectedKey(selectedKey === d.k ? null : d.k)}
                  />
                );
              })}
            </svg>
          </div>

          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, fontSize: 11, color: '#8a95a3' }}>
            <span>Lower</span>
            <div style={{
              width: 160, height: 8, borderRadius: 4,
              background: 'linear-gradient(90deg, rgb(250,238,218), rgb(250,199,117), rgb(239,159,39), rgb(216,90,48), rgb(153,60,29))',
            }} />
            <span>Higher</span>
            <span style={{ marginLeft: 8 }}>
              {colorMode === 'score' ? 'Priority score' : colorMode === 'u5mr' ? 'Modeled U5MR' : 'Uncertainty (CI width)'}
            </span>
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 12, height: 12, border: '1.5px solid #f5f3ee', borderRadius: 2, display: 'inline-block', opacity: 0.7 }} />
              Top-{budgetN} outlined
            </span>
          </div>

          {/* Weight sliders */}
          <div style={{ marginTop: 22, background: '#161d25', border: '1px solid #232b34', borderRadius: 10, padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#f5f3ee' }}>Priority score weights</div>
              <button
                onClick={resetWeights}
                style={{ fontSize: 11, color: '#8a95a3', background: 'none', border: '1px solid #2a323c', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}
              >
                Reset to default (40/30/20/10)
              </button>
            </div>
            {Object.keys(DEFAULT_WEIGHTS).map((key) => (
              <div key={key} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                  <span style={{ color: WEIGHT_COLORS[key] }}>{WEIGHT_LABELS[key]}</span>
                  <span style={{ fontFamily: 'monospace', color: '#c8cdd4' }}>{(weights[key] * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(weights[key] * 100)}
                  onChange={(e) => handleWeightChange(key, Number(e.target.value) / 100)}
                  style={{ width: '100%', accentColor: WEIGHT_COLORS[key] }}
                />
              </div>
            ))}
            <div style={{ fontSize: 11, color: '#6b7482', marginTop: 6, lineHeight: 1.5 }}>
              Weights auto-renormalize to sum to 100%. Default weights (40% mortality risk, 30% uncertainty, 20% access, 10% population) are a literature-informed starting assumption, not a fitted or "correct" answer — adjust them to see how the ranking responds.
            </div>
          </div>
        </div>

        {/* Right: Detail panel + top list */}
        <div style={{ flex: '0 0 380px', borderLeft: '1px solid #2a323c', padding: '20px 22px', background: '#161d25' }}>
          {displayed ? (
            <DistrictDetail d={displayed} isPinned={!!selected} onClose={() => setSelectedKey(null)} />
          ) : (
            <div style={{ fontSize: 13, color: '#6b7482', lineHeight: 1.6 }}>
              Hover or click a district on the map to see its full risk profile, uncertainty, and the reasoning behind its rank.
            </div>
          )}

          <div style={{ marginTop: 24 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#f5f3ee', marginBottom: 10 }}>
              Top {budgetN} priority districts
            </div>
            <div style={{ maxHeight: 380, overflowY: 'auto' }}>
              {topN.map((d) => (
                <div
                  key={d.k}
                  onClick={() => setSelectedKey(d.k)}
                  onMouseEnter={() => setHoveredKey(d.k)}
                  onMouseLeave={() => setHoveredKey(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '7px 8px',
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: selectedKey === d.k ? 'rgba(217,119,87,0.15)' : 'transparent',
                  }}
                >
                  <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#6b7482', width: 20 }}>{d.rank}</span>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: colorFor(d), flexShrink: 0 }} />
                  <span style={{ fontSize: 12.5, color: '#e8e6e0', flex: 1 }}>{d.n}</span>
                  <span style={{ fontSize: 11, color: '#6b7482' }}>{d.prov.split(' ')[0]}</span>
                  {!d.had_data && (
                    <span title="No direct DHS cluster data -- model-based estimate only" style={{ fontSize: 9, color: '#e8956f', border: '1px solid #d97757', borderRadius: 3, padding: '1px 4px' }}>
                      no data
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Footer disclaimer */}
      <div style={{ borderTop: '1px solid #2a323c', padding: '14px 28px', fontSize: 11, color: '#6b7482', lineHeight: 1.6 }}>
        Estimates are MODELED, not observed or official mortality statistics. Built from PBS 2017 Census (district demographics/geography) and PDHS 2017-18 birth-history data (used only in aggregated, district-level, non-identifying form per DHS terms of use). {features.filter(f => !f.had_data).length} of {features.length} districts have zero direct DHS survey clusters and rely entirely on province + covariate pooling — their estimates carry wider uncertainty (see "data uncertainty" color mode). Decision-support only.
      </div>

      {/* Third-party data attribution -- required by source terms, see THIRD_PARTY_DATA_LICENSES.md */}
      <div style={{ borderTop: '1px solid #2a323c', padding: '10px 28px 16px', fontSize: 10.5, color: '#5a6270', lineHeight: 1.6 }}>
        District boundaries: OCHA Pakistan administrative boundaries via HDX (license/version not independently re-verified by this project — see docs/DATA_SOURCES.md). Health facility locations: © OpenStreetMap contributors, via HOTOSM (Open Database License 1.0) — not redistributed as raw points, used only as an aggregated distance covariate. Province-level mortality benchmark: Global Burden of Disease Collaborative Network, GBD 2023 Results, IHME, 2024. Demographic data: Pakistan Bureau of Statistics, 2017 Census. See THIRD_PARTY_DATA_LICENSES.md for full terms.
      </div>
    </div>
  );
}

function DistrictDetail({ d, isPinned, onClose }) {
  return (
    <div style={{ background: '#0d1218', border: '1px solid #232b34', borderRadius: 10, padding: '16px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 11, color: '#8a95a3' }}>{d.prov}</div>
          <div style={{ fontSize: 17, fontWeight: 600, color: '#f5f3ee' }}>{d.n}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 10, color: '#8a95a3' }}>Rank</div>
          <div style={{ fontFamily: 'monospace', fontSize: 20, color: '#e8956f', fontWeight: 600 }}>#{d.rank}</div>
        </div>
      </div>
      {isPinned && (
        <button onClick={onClose} style={{ fontSize: 10, color: '#6b7482', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 4 }}>
          ✕ clear selection
        </button>
      )}

      <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <Stat label="Modeled U5MR" value={`${fmt(d.u5mr)}`} unit="per 1,000" sub={`95% CI ${fmt(d.u5mr_lo)}–${fmt(d.u5mr_hi)}`} color="#d85a30" />
        <Stat label="Priority score" value={fmt(d.score, 3)} unit="" sub={`of 1.000 max`} color="#e8956f" />
        <Stat label="Population" value={fmtInt(d.pop)} unit="" sub="2017 census" color="#85b7eb" />
        <Stat label="Under-5 share" value={fmt(d.u5share)} unit="%" sub="of population" color="#85b7eb" />
      </div>

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #232b34' }}>
        <div style={{ fontSize: 11, color: '#8a95a3', marginBottom: 8 }}>
          Data basis: {d.had_data ? (
            <span style={{ color: '#7fd9b8' }}>{d.n_births} births sampled in PDHS 2017-18 (5yr window)</span>
          ) : (
            <span style={{ color: '#e8956f' }}>no direct DHS clusters — pure province + covariate estimate</span>
          )}
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 11, color: '#8a95a3', marginBottom: 8 }}>Why this rank — component contributions</div>
        <ContribBar label="Mortality risk" value={d.normMort} color="#d85a30" />
        <ContribBar label="Uncertainty" value={d.normUnc} color="#7f77dd" />
        <ContribBar label="Geographic accessibility proxy" value={d.normAcc} color="#5dcaa5" />
        <ContribBar label="Population" value={d.normPop} color="#85b7eb" />
      </div>

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #232b34', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11.5 }}>
        <div><span style={{ color: '#8a95a3' }}>Literacy</span><div style={{ fontFamily: 'monospace', color: '#c8cdd4' }}>{fmt(d.lit)}%</div></div>
        <div><span style={{ color: '#8a95a3' }}>Improved water</span><div style={{ fontFamily: 'monospace', color: '#c8cdd4' }}>{fmt(d.water)}%</div></div>
        <div><span style={{ color: '#8a95a3' }}>Improved sanitation</span><div style={{ fontFamily: 'monospace', color: '#c8cdd4' }}>{fmt(d.sani)}%</div></div>
        <div><span style={{ color: '#8a95a3' }}>Deprivation index</span><div style={{ fontFamily: 'monospace', color: '#c8cdd4' }}>{fmt(d.dep, 2)}</div></div>
      </div>
    </div>
  );
}

function Stat({ label, value, unit, sub, color }) {
  return (
    <div style={{ background: '#161d25', borderRadius: 8, padding: '8px 10px' }}>
      <div style={{ fontSize: 10, color: '#8a95a3' }}>{label}</div>
      <div style={{ fontFamily: 'monospace', fontSize: 16, fontWeight: 600, color }}>
        {value}<span style={{ fontSize: 10, color: '#6b7482', fontWeight: 400 }}> {unit}</span>
      </div>
      <div style={{ fontSize: 9.5, color: '#6b7482' }}>{sub}</div>
    </div>
  );
}

function ContribBar({ label, value, color }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: '#8a95a3', marginBottom: 2 }}>
        <span>{label}</span>
        <span style={{ fontFamily: 'monospace' }}>{fmt(value * 100, 0)}%</span>
      </div>
      <div style={{ height: 5, background: '#1c242c', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value * 100}%`, background: color, borderRadius: 3 }} />
      </div>
    </div>
  );
}
