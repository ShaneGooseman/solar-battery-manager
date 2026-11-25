# Solar Battery Manager

[🇪🇸 Documentación en español](README.md) · [📋 Changelog](CHANGELOG.md)

Custom integration for **Home Assistant Core (2026.11+)** that estimates tomorrow's daytime photovoltaic surplus and calculates the **minimum target SOC at the end of the off-peak grid window** (default `08:00`) so daytime solar generation can charge the battery to 100%.

> **Safe by default (`v0.2.4`)**: the integration runs in **simulation mode** while **`Real inverter control`** is turned off (`OFF` by default). When explicitly enabled, it only updates the overnight Program SOC target (`number.inversordeye_program_1_soc`) and never modifies voltages, max currents, or BMS protections.

---

## Daily Operation Cycle

1. **Solar daytime (sunrise → sunset)**:
   - Keeps night idle SOC (`20%`) and pauses `recorder` queries and continuous recalculation during daylight (`solar_window_paused: true`).
   - Your inverter charges the battery normally from solar.
2. **Sunset**:
   - Captures today's total PV production once (if configured) for next-day forecast error comparison.
   - Resumes calculation for the upcoming night using daytime load history and tomorrow's PV forecast.
3. **Pre-midnight freeze (`23:55`)**:
   - Freezes and persists the **target SOC** in Home Assistant storage so midnight sensor resets or HA restarts do not alter the overnight plan.
4. **Off-peak grid window (`00:00–08:00`)**:
   - **Before recommended start time**: keeps **night idle SOC** (`20%`), allowing normal battery discharge at night.
   - **Once recommended start time is reached** (based on max grid charging current): writes **target SOC** and **latches** until `08:00` to prevent chattering if actual charge power differs.
   - **At `08:00`**: restores night idle SOC (`20%`).

---

## How Target SOC Is Calculated (Formulas)

The integration **does not** assume nominal battery capacity equals usable capacity, and does not subtract 24-hour house load (since nighttime consumption can be covered by the grid).

1. **Daytime house load estimation (`daytime_load_kWh`)**:
   - Queries `recorder` hourly statistics strictly between **sunrise and sunset** (`sun.sun`) over the last *N* days (`14` default).
   - Discards incomplete days (`< 75%` valid hours) or invalid values; requires at least `3` valid days.
   - Uses **`Median`** *(default, resilient against spikes)* or **`Mean`**.

2. **Estimated daytime solar surplus (`surplus_kWh`)**:
```text
surplus_kWh = max(0, pv_forecast_tomorrow_kWh - daytime_load_kWh)
```

3. **Expected solar SOC gain (`solar_soc_gain_%`)**:
```text
solar_soc_gain_% = (surplus_kWh * charge_efficiency / usable_battery_kWh) * 100
```

4. **Target SOC at the end of the off-peak window**:
```text
raw_target_SOC_% = 100 - solar_soc_gain_% + safety_margin_%
target_SOC_%     = round(min(max_operational_SOC, max(min_operational_SOC, raw_target_SOC_%)))
```

5. **Simulated grid energy & recommended start time**:
```text
delta_SOC       = max(0, target_SOC_% - current_SOC_%)
grid_energy_kWh = ((delta_SOC / 100) * usable_battery_kWh) / charge_efficiency
charge_power_kW = (max_grid_current_A * nominal_voltage_V) / 1000
net_energy_kWh  = (delta_SOC / 100) * usable_battery_kWh
duration_min    = ceil((net_energy_kWh / charge_power_kW) * 60) + buffer_minutes
start_time      = max(tariff_start, tariff_end - duration_min)
```

> **Note**: this is a simplified energy model; reaching 100% is not guaranteed under inverter/BMS power limits or large PV forecast errors.

---

### Step-by-step numerical example

With `11.91 kWh` PV forecast, `5.10 kWh` daytime load, `12.0 kWh` usable capacity, `90%` efficiency, `5%` margin, `40%` current SOC, and `25 A @ 51.2 V` (`15 min` buffer):

1. **Surplus**: `max(0, 11.91 - 5.10) = 6.81 kWh`
2. **Solar gain**: `(6.81 * 0.90 / 12.0) * 100 = 51.08%`
3. **Target SOC**: `100 - 51.08 + 5 = 53.92 -> 54%`
4. **Charge plan** (`delta_SOC = 54 - 40 = 14%`):
   - Net energy: `1.68 kWh` | Estimated grid energy: `1.87 kWh`
   - Charge power: `25 * 51.2 / 1000 = 1.28 kW`
   - Duration: `ceil((1.68 / 1.28) * 60) + 15 = 94 min` → **Recommended start: `06:26`**

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
| `PV forecast error` | `sensor` (`kWh`) | Difference between yesterday's total PV and yesterday's frozen forecast |
| `Model status` | `sensor` (`enum`) | Calculation status, solar pause, latch, and last control action |
| `Calculation ready` | `binary_sensor` | Indicates whether current calculation is valid and usable |
| `Real inverter control` | `switch` | Opt-in switch to enable Program 1 SOC writes (`OFF` by default) |

---

## Safety & Fail-Safe Design

- **Freshness checks (`last_reported`)**: if PV forecast is older than `24h` or SOC older than `30m`, calculation turns invalid and **refuses to order charge** (`fail_safe_hold`). Static settings like max charge current do not expire.
- **Explicit energy units**: only `kWh` and `Wh` are accepted; missing units fail safely.
- **Write verification**: in real control mode, polls up to `5s × 2 attempts` to verify the updated state.
- **Switch-off behavior**: restores night idle SOC (`20%`) before returning to simulation mode.

---

## Installation via HACS

1. Open **HACS → Integrations → `⋮` → Custom repositories**.
2. Add `https://github.com/ShaneGooseman/solar-battery-manager` (category **Integration**).
3. Install **Solar Battery Manager** and **restart Home Assistant**.
4. Go to **Settings → Devices & services → Add integration → Solar Battery Manager**.

---

## Unit Tests & Technical Docs

```powershell
python -m unittest discover -s tests/unit -v
```
*(On Windows, `tzdata` is required for `ZoneInfo("Europe/Madrid")`.)*

- [CHANGELOG.md](CHANGELOG.md) — Version history.
- [AGENTS.md](AGENTS.md) — Safety and architecture rules.
- [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) — Current technical specification.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Phase status.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — Initial installation context.
