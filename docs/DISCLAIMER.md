# Risk Disclaimer & Responsible Use

**AccuScan is a research, analytics and risk-monitoring system. It is NOT financial advice, NOT a
guaranteed-profit system, and NOT a claim of any exploit, edge or "loophole".**

## Key facts you must accept before using any execution mode

1. **You can lose money — including your entire stake.** Deriv Accumulator Options pay out only
   while the spot stays inside a per-tick range; a single tick outside the range is a knockout and
   the stake is lost.

2. **Synthetic indices are engineered to be difficult to predict.** They are designed with
   well-defined statistical properties and a built-in house margin. No tick/digit pattern is a
   reliable predictor of future ticks. The digit-risk signal in this system is an explicitly
   **configurable hypothesis** used as a screening veto, and must be validated with replay /
   backtesting before being trusted.

3. **Higher growth rate ⇒ narrower range ⇒ higher knockout probability per tick.** The "adaptive
   growth governor" recommends rates based on current conditions and never simply picks the maximum.

4. **Backtest / replay results are not predictive of live results.** The paper/replay barrier model
   is a documented approximation, not Deriv's exact barrier. Live spreads, latency, slippage,
   re-quotes and feed gaps will differ.

5. **No martingale. No averaging down. No automatic stake increase after a loss.** These are not
   merely disabled by configuration — they are not expressible through the trading API in this
   codebase.

## Safe-by-default design

- Default mode is **analytics** (observe only). Modes escalate explicitly:
  `analytics → paper → demo → live`.
- The public market scanner needs **no API token**. A token is required only for demo/live.
- **Use a Deriv demo account token first.** Validate behaviour for an extended period before
  considering real funds.
- Live trading additionally requires the environment variable
  `ACCUSCAN_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK`. If it is absent, live entries are refused.
- Every entry passes an AND-ed safeguard gate (daily-loss cap, trade-rate caps, loss cooldown,
  readiness persistence, data-quality health, no active critical alert, growth-rate cap).

## Legal / regulatory

- Accumulator Options and synthetic indices may be **restricted or prohibited** in your
  jurisdiction. It is your responsibility to comply with all applicable laws and with Deriv's terms
  of service and API usage policies.
- Use your own registered `app_id` and API tokens. Never share tokens. Grant the **minimum** scopes
  required (`read`, `trade`); this system never needs `payments` or `admin`.
- This software is provided "as is", without warranty of any kind. The authors accept no liability
  for any loss arising from its use.

## Responsible use checklist

- [ ] I have read and understood the code paths that place orders.
- [ ] I am using a demo account / token for evaluation.
- [ ] I have run replay/backtests and reviewed the metrics critically.
- [ ] I have set conservative safeguard limits I am comfortable losing.
- [ ] I understand AccuScan reduces and explains risk, but cannot remove it.
