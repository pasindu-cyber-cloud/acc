# Scoring, Stability, Deterioration & Health — Formula Reference

All sub-scores are on a **0–100 "higher = safer/better"** scale unless noted. All movement is
measured in **pips** (`quote_delta / pip_value`) so thresholds are comparable across symbols.

> **Why per-tick tails dominate.** A Deriv Accumulator pays while the spot stays inside a band that
> is **recalculated each tick around the previous spot** and is **narrower at higher growth rates**.
> A knockout is therefore a *single* tick whose move exceeds the band. Cumulative range and trend
> barely matter; what matters is the **upper tail of per-tick moves relative to the typical move**.
> The model is built accordingly.

---

## 1. Movement features (per window)

Given per-tick deltas in pips `d[1..n]`, `a = |d|`:

- `mean_abs = mean(a)`, `median_abs = median(a)`, `std_delta = std(d)`
- `zero/small/large` counts via `zero_move_eps`, `large_move_pips`
- `jump_count`: `a_i > jump_sigma · std_delta`
- `jump_proxy = Σ(a_i² over jumps) / Σ(a_i²)`  — tail share of movement energy
- `avg_adverse_move = mean(runningMax(cumsum(d)) − cumsum(d))` — average drawdown of the path
- `movement_cluster = max(0, lag-1 autocorr(|d|))` — ARCH-like volatility clustering
- `chop_score = fraction of sign flips`; `direction_persistence = 1 − chop_score`
- **Tail metrics:** `p95, p99 = percentile(a)`, `tail_ratio = p99 / median_abs`
  (Gaussian baseline `p99/median ≈ 3.8`; higher ⇒ fat tails / jumps.)

## 2. Digit features (per window)

- `distribution[d]`, `danger_count`, `danger_pct` for configurable `danger_digits` (default `0,1,5`)
- `cluster_score` = share of consecutive danger-digit gaps ≤ `cluster_distance`
- `burst_count`, `drought_len`, `entropy` (bits, max `log2 10 ≈ 3.32`)

## 3. Accumulator Stability Model

```
tail_risk        = clamp((tail_ratio − 3.8) / 6)
jump_burst_prob  = clamp(0.55·tail_risk + 0.25·jump_proxy + 0.20·movement_cluster)
core_risk        = clamp(0.60·tail_risk + 0.25·jump_proxy + 0.15·clamp(large_freq·8))
growth_pressure  = clamp((growth_rate − 0.01) / 0.04)            # 0 at 1%, 1 at 5%
barrier_risk     = clamp(core_risk·(0.6 + 0.4·growth_pressure) + 0.15·growth_pressure)
calmness         = clamp(1 − 0.7·tail_risk − 0.3·movement_cluster)
smoothness       = clamp(1 − micro_vol_ratio / 2.5)
stability_persistence = clamp(1 − |ln(std_primary / std_short)|)

stability_score  = 100 · clamp(
      0.35·(1 − barrier_risk)
    + 0.30·calmness
    + 0.15·stability_persistence
    + 0.10·(1 − jump_burst_prob)
    + 0.10·smoothness ) · (1 − 0.4·jump_burst_prob)
```

`barrier_risk` is **monotonically increasing in growth rate** (verified: ≈0.13 → 0.37 from 1%→5% on
calm data), encoding "higher growth ⇒ tighter band ⇒ more risk".

## 4. Market Quality Score (MQS)

```
MQS = Σ wᵢ · sub_scoreᵢ          (weights renormalised to sum to 1.0)
```

| Sub-score | Weight | Formula sketch |
|---|---|---|
| `digit_clean_100` | 0.15 | `100·clamp(1 − penalty)`, penalty gated by danger **excess** |
| `digit_clean_25` | 0.10 | same on 25-tick window |
| `movement_risk` | 0.15 | `100·clamp(1 − (0.5·tail_risk + 0.25·jump_proxy + 0.15·large_freq + 0.10·chop))` |
| `accu_stability` | 0.20 | `stability_score` |
| `jump_safety` | 0.15 | `100·(1 − jump_burst_prob)` |
| `trend_smooth` | 0.10 | `100·clamp(0.6·smoothness + 0.4·(1 − chop))` |
| `risk_fit` | 0.05 | profile floors / family fit |
| `deterioration_resist` | 0.05 | `100·clamp(0.7·persistence + 0.3·(1 − decay))` |
| `data_quality` | 0.05 | freshness + latency + gaps |

**Digit cleanliness** penalty (note the excess gate that prevents false alarms on uniform data):

```
excess         = max(0, danger_pct − expected)          # expected = |danger_digits| / 10
excess_factor  = clamp(excess / 0.15)
penalty        = 1.6·excess + 0.5·cluster·excess_factor + 0.10·min(bursts,5)·excess_factor
                 + entropy_penalty(if entropy < floor)
```

**Veto layer** (forces HIGH_RISK, caps MQS < WATCH). Digit vetoes use binomial significance:

```
z_w = (danger_count − n·p) / sqrt(n·p·(1−p)),   p = |danger_digits| / 10
veto if:
  z_25  ≥ danger_z_short (3.0)                              -> danger_digit_excess_25
  z_100 ≥ danger_z_primary (3.0) AND cluster_100 ≥ 0.7      -> danger_digit_cluster_100
  jump_burst_prob ≥ 0.5                                     -> jump_burst_probability
  tail_excess_25/6 ≥ 0.6 AND jump_count_25 ≥ 1              -> short_window_tail_jump
  data_quality < 50 OR not fresh                            -> data_quality
```

## 5. Status & confidence

```
READY      if MQS ≥ profile.ready_threshold and no veto
WATCH      if MQS ≥ watch_threshold (55)
HIGH_RISK  otherwise (or any veto)
actionable = READY and ready_persistence ≥ min_ready_persistence_ticks
confidence = clamp(0.5·data_sufficiency + 0.3·threshold_decisiveness + 0.2·data_quality)
```

## 6. Deterioration score (post-entry)

Entry baseline freezes `{mqs, stability, volatility, jump_risk, trend_slope, danger_rate,
movement_risk, rolling_range, data_quality}`. Each tick:

```
c_score_drop = clamp((mqs_base − mqs) / score_drop_crit)
c_vol        = clamp((vol/vol_base − 1) / 2)
c_cusum      = clamp(cusum / h)        # CUSUM on standardised vol deviation, capped at 2h
c_z          = clamp((|z| − z_warn)/(z_crit − z_warn))   # rolling z on realised vol
c_jump       = clamp(Δjump_risk / 0.4)
c_burst      = clamp(burst_count / 5)
c_trend      = trend contradiction vs baseline
c_danger     = clamp(Δdanger_pct / 0.2)
c_latency, c_stale from data quality

deterioration = 100·clamp(0.24·c_score_drop + 0.18·c_vol + 0.12·c_cusum + 0.10·c_z
              + 0.12·c_jump + 0.06·c_burst + 0.06·c_trend + 0.04·c_danger
              + 0.04·c_latency + 0.04·c_stale)
```

Health label bands: `<20 HEALTHY, <40 WATCH_CLOSELY, <60 DETERIORATING, <80 CRITICAL, else
EXIT_IF_POSSIBLE`. Alert level CRITICAL if `deterioration ≥ 70`, `score_drop ≥ 20`, CUSUM triggered,
`|z| ≥ 3.5`, latency ≥ crit, or feed not fresh.

## 7. Trade Health Meter (baseline-relative)

```
health = 100 · Σ wⱼ · componentⱼ      (each component in [0,1], 1 = as good as entry)
components: mqs_delta, stability_delta, volatility_delta, jump_delta, trend_delta,
            danger_increase, data_quality, time_in_trade
labels: ≥80 HEALTHY, ≥65 WATCH_CLOSELY, ≥45 DETERIORATING, ≥25 CRITICAL, else EXIT_IF_POSSIBLE
```

## 8. Adaptive growth governor

Evaluate each allowed rate `r ≤ profile.max_growth_rate`; recompute stability at `r`. Pick the
**highest** `r` such that `stability(r) ≥ profile.stability_floor + 5` **and**
`jump_safety(r) ≥ profile.jump_safety_floor` **and** `deterioration ≤ 30`. Otherwise default to the
minimum rate. (Never "high just because aggressive".)

## 9. Tuning / validation note

All weights, thresholds and `danger_digits` are configurable in `config/default.yaml` and
`config/risk_profiles.yaml`. **Every threshold is a hypothesis** and should be re-validated with the
replay engine (`accuscan.backtest`) on representative data, including the threshold-sensitivity
table it produces.
