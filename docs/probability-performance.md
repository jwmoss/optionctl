# Reduce scan CPU time

`scan_ticker` computes a call probability for every retained contract. `simulate_p_itm` generates 25,000 normal draws, pairs them with their negatives, and evaluates 50,000 terminal prices per contract.

Under the current zero-drift lognormal model, the same event has a closed-form probability. For positive inputs, let `a = sigma * sqrt(t)` and `z = log(s0 / k) / a - a / 2`. The probability equals `0.5 * erfc(-z / sqrt(2))`.

For 1,000 contract inputs, the existing function took 534 ms and a scalar closed-form prototype took 0.253 ms. Each value is the median of five runs. Inputs used spot 100, strikes 90 through 110, volatility 0.45, and maturities of 1 through 15 days. This benchmark isolates the calculation.

- [ ] Compare results across extreme strikes, near-expiry contracts, and invalid inputs. Preserve the current invalid-input behavior.
- [ ] Check scoring, saved predictions, and the documented Monte Carlo behavior before changing the default.
- [ ] Measure the complete scan against one fixed input set. Track provider fetch time separately.
