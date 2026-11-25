# Solar Battery Manager

[🇪🇸 Documentación en español](README.md)

Custom integration for **Home Assistant Core (2026.11+)** that estimates next-day daytime photovoltaic surplus and calculates the **minimum target SOC** at the end of the off-peak grid window (default `00:00–08:00`) so solar generation can charge the battery to 100%.

> **Current status: Simulation by default with opt-in real control (`v0.2.3`)**
> The **`Real inverter control`** switch is **OFF by default** (read-only simulation). Only if you explicitly enable it will the integration update `number.inversordeye_program_1_soc` with post-write verification (up to ~10s with retry). Turning the switch off restores `20%` (`night_idle_soc`) as a final safe write. It never modifies BMS or inverter protections.

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
```text
surplus_kWh = max(0, pv_forecast_tomorrow_kWh - daytime_load_kWh)
```

### 4. Expected solar SOC gain (`solar_soc_gain_%`)
```text
solar_soc_gain_% = (surplus_kWh * charge_efficiency / usable_battery_kWh) * 100
```

Where:
- `usable_battery_kWh` is the user-configured real usable capacity (not nominal).
- `charge_efficiency` is the configured charge efficiency (e.g. `0.90` for `90%`).

### 5. Target SOC at the end of the off-peak window (`08:00`)
```text
raw_target_SOC_% = 100 - solar_soc_gain_% + safety_margin_%
target_SOC_%     = round(min(max_operational_SOC, max(min_operational_SOC, raw_target_SOC_%)))
```

### 6. Simulated grid energy required (`grid_energy_kWh`)
```text
delta_SOC       = max(0, target_SOC_% - current_SOC_%)
grid_energy_kWh = ((delta_SOC / 100) * usable_battery_kWh) / charge_efficiency
```

### 7. Recommended grid charge start time
Using the configured max grid charging current (in A) and nominal battery voltage (default `51.2 V`):

```text
charge_power_kW = (max_grid_current_A * nominal_voltage_V) / 1000
net_energy_kWh  = (delta_SOC / 100) * usable_battery_kWh
duration_min    = ceil((net_energy_kWh / charge_power_kW) * 60) + buffer_minutes
start_time      = max(tariff_start, tariff_end - duration_min)
```

If `duration_min` exceeds the off-peak window length, start time is clamped to `tariff_start` (`00:00`) and flagged in entity attributes (`can_reach_target_in_window: false`).

### 8. Pre-midnight freeze & daytime solar pause
- **Freeze (`23:55`)**: when the configured freeze time is reached, the **target SOC** is frozen and persisted in Home Assistant storage for the entire overnight window (`00:00–08:00`), preventing midnight sensor resets or Home Assistant restarts from altering the target.
- **Daytime solar pause (sunrise–sunset)**: once daytime idle SOC is ensured, the integration pauses `recorder` queries and SOC recalculation during solar hours (`solar_window_paused: true`), updating only **`PV forecast error`** in memory. It resumes automatically at sunset.
- **Opt-in Deye control (`Real inverter control`, OFF by default)**:
  - Before the recommended start time and outside `00:00–08:00`: keeps **night idle SOC** (`20%` default).
  - Once the recommended start time is reached (`should_charge_now: true`): writes the **target SOC** to `number.inversordeye_program_1_soc`, **latches** until `08:00` to prevent chattering, and verifies after writing (up to 5s × 2 attempts).
  - If any input is invalid or stale (`last_reported` > 24h forecast or > 30m SOC; `Calculation ready: off`), it never orders grid charging (`fail_safe_hold`).
  - Turning the switch off manually performs one final write restoring `night_idle_soc` (`20%`).

---

### Step-by-step numerical example

Assume:
- Tomorrow PV forecast: `11.91 kWh`
- Estimated daytime load (median): `5.10 kWh`
- Usable capacity: `12.0 kWh` | Efficiency: `90%` | Safety margin: `5%`
- Current SOC: `40%` | Max grid current: `25 A` @ `51.2 V` | Time buffer: `15 min`

1. **Surplus**: `max(0, 11.91 - 5.10) = 6.81 kWh`
2. **Solar SOC gain**: `(6.81 * 0.90 / 12.0) * 100 = 51.08%`
3. **Target SOC**: `100 - 51.08 + 5 = 53.92 -> 54%`
4. **Required grid charge** (`delta_SOC = 54 - 40 = 14%`):
   - Net energy to add: `0.14 * 12.0 = 1.68 kWh`
   - Estimated grid energy: `1.68 / 0.90 = 1.87 kWh`
   - Charge power: `25 * 51.2 / 1000 = 1.28 kW`
   - Duration: `ceil((1.68 / 1.28) * 60) + 15 = 79 + 15 = 94 min`
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
| `PV forecast error` | `sensor` (`kWh`) | Difference between yesterday's total PV (captured at freeze) and yesterday's frozen forecast |
| `Model status` | `sensor` (`enum`) | Calculation status, solar pause, and last control action |
| `Calculation ready` | `binary_sensor` | Indicates whether current calculation is valid and usable |
| `Real inverter control` | `switch` | Opt-in switch to enable Program 1 SOC writes (OFF by default) |

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
