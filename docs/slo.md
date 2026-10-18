# Service Level Objectives (SLOs) & Multi-Window Burn-Rate Alerting

This document outlines the Service Level Indicators (SLIs), Service Level Objectives (SLOs), error budget calculations, and alerting strategies implemented in this repository.

---

## 1. SLIs and SLOs

### Availability SLO: 99.5% over 30 days
- **Service Level Indicator (SLI):**
  $$\text{Availability SLI} = 1 - \frac{\sum \text{rate}(http\_requests\_total\{status=\sim'5..'\}[\Delta t])}{\sum \text{rate}(http\_requests\_total[\Delta t])}$$
- **Error Budget:** $100\% - 99.5\% = 0.5\%$ bad requests.
- **Allowed Downtime / Error Equivalent:** Over a 30-day window ($30 \times 24 = 720\text{ hours}$), $0.5\%$ corresponds to approximately **3 hours and 36 minutes**.

### Latency SLO: 95.0% of requests served under 500 ms over 30 days
- **Service Level Indicator (SLI):**
  $$\text{Latency SLI} = \frac{\sum \text{rate}(http\_request\_duration\_seconds\_bucket\{le='0.5'\}[\Delta t])}{\sum \text{rate}(http\_request\_duration\_seconds\_count[\Delta t])}$$
- **Error Budget:** $100\% - 95.0\% = 5.0\%$ slow requests.

---

## 2. Error Budget Arithmetic & Burn Rates

Burn rate ($B$) represents how fast the system is consuming its allocated error budget relative to the 30-day target:
$$B = \frac{\text{Observed Bad Request Ratio}}{\text{Error Budget}}$$

- **$1\times$ Burn Rate:** Exactly 100% of the error budget is consumed over 30 days (steady-state limit).
- **$14.4\times$ Burn Rate (Fast Burn):** Consumes 2% of the budget in 1 hour; exhausts the entire 30-day budget in 50 hours.
- **$6\times$ Burn Rate (Slow Burn):** Consumes 5% of the budget in 6 hours; exhausts the entire 30-day budget in 120 hours (5 days).

---

## 3. Multi-Window Multi-Burn-Rate Alerting

Single threshold alerts (e.g. `error_rate > 1%`) suffer from two fundamental flaws:
1. **Short windows** trigger frequent false alarms on temporary, self-resolving spikes.
2. **Long windows** take hours to reset after an incident resolves, creating alert fatigue.

Google SRE best practice resolves this using **multi-window alerts**: each alert rule requires **both a long window and a short window** to exceed the burn rate threshold simultaneously.
- The **long window** ensures the consumption is statistically significant.
- The **short window** ensures the issue is actively ongoing (preventing alerts after the problem stops).

### Comparison: Demo vs. Production Windows

In this demonstration, Prometheus TSDB retention is set to 2 hours (`--storage.tsdb.retention.time=2h`) to fit within our strict WSL memory budget. Alert evaluation windows are scaled down accordingly:

| Alert Name | Severity | SLO | Threshold | Long Window (Demo) | Short Window (Demo) | Long Window (Prod) | Short Window (Prod) |
|---|---|---|---|---|---|---|---|
| **AvailabilityFastBurn** | `page` | Availability | $14.4 \times 0.5\% = 7.2\%$ | 5 min | 1 min | 1 hour | 5 min |
| **AvailabilitySlowBurn** | `ticket` | Availability | $6.0 \times 0.5\% = 3.0\%$ | 30 min | 5 min | 6 hours | 30 min |
| **LatencyBudgetBurn** | `ticket` | Latency | $6.0 \times 5.0\% = 30.0\%$ | 5 min | 1 min | 6 hours | 30 min |
| **TaskApiDown** | `page` | Infrastructure | $up == 0$ | 30s | N/A | 1 min | N/A |
