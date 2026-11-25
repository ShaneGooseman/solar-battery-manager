# Solar Battery Manager

[🇪🇸 Documentación en español](README.md)

Custom integration for **Home Assistant Core (2026.11+)** that estimates next-day daytime photovoltaic surplus and calculates the **minimum target SOC** at the end of the off-peak grid window (default `00:00–08:00`) so solar generation can charge the battery to 100%.

> **Current mode: Read-only simulation (`v0.1.5`)**
> This version **never writes to the inverter** and never modifies BMS protection parameters. All calculations and recommendations are exposed as read-only entities for validation.

---

## How Target SOC Is Calculated (Full Transparency)

The integration **does not** assume nominal battery capacity equals usable capacity, and does not subtract 24-hour house load (since nighttime consumption can be covered by the grid). Every calculation follows these 8 explicit steps:

### 1. Daytime solar window (`Sun`)
Using the configured `Sun` entity (`sun.sun` by default), the integration reads local **sunrise** (`next_rising`) and **sunset** (`next_setting`).
- If the `Sun` entity is missing, `unavailable`, or lacks both attributes, the calculation **fails safely** (`Invalid Sun solar window`) without guessing values.

### 2. Daytime house load estimation (`daytime_load_kWh`)
It queries Home Assistant `recorder` hourly long-term statistics for the configured load energy sensor, summing **only the hours between sunrise and sunset** over the last *N* days (`lookback_days`, default 14).
- Days with missing data or negative/non-finite values are discarded and recorded in `samples_used` and `samples_discarded` attributes.
- If valid days are fewer than `min_history_days` (default 3), the calculation fails safely (`Insufficient history`).
- Aggregation method:
  - **`Median`** *(default)*: resilient against occasional appliance spikes.
  - **`Mean`**: arithmetic mean across valid days.

### 3. Estimated daytime solar surplus (`surplus_kWh`)
$$\text{surplus\_kWh} = \max\bigl(0,\; \text{pv\_forecast\_tomorrow\_kWh} - \text{daytime\_load\_kWh}\bigr)$$

### 4. Expected solar SOC gain (`solar_soc_gain_%`)
$$\text{solar\_soc\_gain\_\%} = \frac{\text{surplus\_kWh} \times \eta_{\text{charge}}}{\text{usable\_battery\_kWh}} \times 100$$

Where:
- $\text{usable\_battery\_kWh}$ is the user-configured real usable capacity (not nominal).
- $\eta_{\text{charge}}$ is the configured charge efficiency (e.g. `0.90` for `90%`).

### 5. Target SOC at the end of the off-peak window (`08:00`)
$$\text{raw\_target\_SOC\_\%} = 100 - \text{solar\_soc\_gain\_\%} + \text{safety\_margin\_\%}$$

$$\text{target\_SOC\_\%} = \text{round}\Bigl(\min\bigl(\text{max\_operational\_SOC},\; \max(\text{min\_operational\_SOC},\; \text{raw\_target\_SOC\_\%})\bigr)\Bigr)$$

### 6. Simulated grid energy required (`grid_energy_kWh`)
$$\Delta\text{SOC} = \max\bigl(0,\; \text{target\_SOC\_\%} - \text{current\_SOC\_\%}\bigr)$$

$$\text{grid\_energy\_kWh} = \frac{(\Delta\text{SOC} / 100) \times \text{usable\_battery\_kWh}}{\eta_{\text{charge}}}$$

### 7. Recommended grid charge start time
Using the configured max grid charging current (in A) and nominal battery voltage (default `51.2 V`):

$$P_{\text{charge\_kW}} = \frac{I_{\text{max\_grid\_A}} \times V_{\text{nominal\_V}}}{1000}$$

$$\text{net\_energy\_kWh} = \frac{\Delta\text{SOC}}{100} \times \text{usable\_battery\_kWh}$$

$$\text{duration\_min} = \left\lceil \frac{\text{net\_energy\_kWh}}{P_{\text{charge\_kW}}} \times 60 \right\rceil + \text{buffer\_minutes}$$

$$\text{start\_time} = \max\bigl(\text{tariff\_start},\; \text{tariff\_end} - \text{duration\_min}\bigr)$$

If $\text{duration\_min}$ exceeds the off-peak window length, start time is clamped to `tariff_start` (`00:00`) and flagged in entity attributes (`can_reach_target_in_window: false`).

### 8. Pre-midnight target freeze
When the configured freeze time is reached (default `23:55`), the **target SOC** is frozen and persisted in Home Assistant storage for the entire overnight window (`00:00–08:00`), preventing midnight sensor resets or Home Assistant restarts from altering the target.

---

### Step-by-step numerical example

Assume:
- Tomorrow PV forecast: `11.91 kWh`
- Estimated daytime load (median): `5.10 kWh`
- Usable capacity: `12.0 kWh` | Efficiency: `90%` | Safety margin: `5%`
- Current SOC: `40%` | Max grid current: `25 A` @ `51.2 V` | Time buffer: `15 min`

1. **Surplus**: $\max(0,\; 11.91 - 5.10) = \mathbf{6.81\text{ kWh}}$
2. **Solar SOC gain**: $(6.81 \times 0.90 / 12.0) \times 100 = \mathbf{51.08\%}$
3. **Target SOC**: $100 - 51.08 + 5 = 53.92 \rightarrow \mathbf{54\%}$
4. **Required grid charge** ($\Delta\text{SOC} = 54 - 40 = 14\%$):
   - Net energy to add: $0.14 \times 12.0 = 1.68\text{ kWh}$
   - Estimated grid energy: $1.68 / 0.90 = \mathbf{1.87\text{ kWh}}$
   - Charge power: $25 \times 51.2 / 1000 = \mathbf{1.28\text{ kW}}$
   - Duration: $\lceil (1.68 / 1.28) \times 60 \rceil + 15 = 79 + 15 = \mathbf{94\text{ min}}$
   - Recommended start time (to finish by `08:00`): **`06:26`**

---

## Entities Created

| Entity | Type | Description |
| :--- | :--- | :--- |
| `PV forecast tomorrow` | `sensor` (`kWh`) | Normalized tomorrow PV forecast |
| `Daytime load forecast tomorrow` | `sensor` (`kWh`) | Estimated daytime load + used/discarded sample trace |
| `Estimated solar surplus tomorrow` | `sensor` (`kWh`) | Estimated daytime solar surplus |
| `Target SOC at 08:00` | `sensor` (`%`) | Calculated target SOC + traceability and freeze attributes |
| `Simulated grid energy required` | `sensor` (`kWh`) | Theoretical grid energy needed from current SOC |
| `Recommended charge start` | `sensor` (`timestamp`) | Calculated start time based on max charging current |
| `Model status` | `sensor` (`enum`) | Calculation status (`OK`, `Insufficient history`, etc.) |
| `Calculation ready` | `binary_sensor` | Indicates whether current calculation is valid and usable |

---

## Installation via HACS

1. Open **HACS** in Home Assistant.
2. Go to **Integrations** → top-right menu (`⋮`) → **Custom repositories**.
3. Add this repository URL with category **Integration**.
4. Search for **Solar Battery Manager** and install it.
5. **Restart Home Assistant**.
6. Go to **Settings → Devices & services → Add integration** and select **Solar Battery Manager**.

---

## Unit Tests (Development)

The pure calculation engine and hourly aggregation are decoupled from Home Assistant and can be run locally with Python 3.13+:

```powershell
python -m unittest discover -s tests/unit -v
```

*(On Windows, `tzdata` is required for `ZoneInfo("Europe/Madrid")`.)*

---

## Technical Documentation

- [AGENTS.md](AGENTS.md) — Project safety and architecture rules.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — Installation context.
- [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) — Functional specification.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Incremental roadmap.
