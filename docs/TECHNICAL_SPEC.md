# Especificación técnica — Solar Battery Manager (v0.2.1)

## 1. Comportamiento funcional

La integración (compatible con **Home Assistant Core 2026.11+**) realiza el siguiente ciclo:

1. Obtener previsión de producción fotovoltaica para el día siguiente desde la entidad seleccionada (`sensor.pv_forecast_total_tomorrow`).
2. Obtener la ventana solar diurna (amanecer y atardecer) desde la entidad `Sun` configurada (`sun.sun` por defecto, atributos `next_rising` y `next_setting`). Si falta o es inválida, falla de forma segura (`invalid_sun_window`).
3. Estimar el consumo de la vivienda **únicamente durante la ventana solar diurna** a partir de las estadísticas horarias del `recorder` (`statistics_during_period`), usando `median` (por defecto) o `mean` sobre los últimos *N* días válidos (`lookback_days = 14`, `min_history_days = 3`).
4. Calcular el excedente solar diurno previsto y convertirlo en ganancia de SOC y **SOC objetivo** al finalizar la ventana económica (`08:00`), con capacidad útil configurable, eficiencia y margen de seguridad.
5. Calcular la **hora de inicio de carga recomendada** a partir de la corriente máxima de carga desde red (`number.inversordeye_battery_grid_charging_current`), la tensión nominal configurable (`51,2 V`) y un margen de tiempo (`15 min`).
6. Congelar y persistir el objetivo diario antes de medianoche (`23:55`) en `Store` para que los reinicios de sensores a las `00:00` o reinicios de HA no alteren el objetivo.
7. Pausar las consultas al `recorder` y el recálculo de SOC durante la ventana solar diurna (`solar_window_paused = True`), manteniendo únicamente el seguimiento en memoria de **`Error de previsión FV`**.
8. Modo simulación por defecto; el control real sobre `number.inversordeye_program_1_soc` es **opt-in** mediante el interruptor `Control real del inversor` (apagado por defecto).

## 2. Fórmulas implementadas (`engine/calculator.py`)

- `surplus_kwh = max(0.0, pv_forecast_kwh - daytime_load_forecast_kwh)`
- `solar_soc_gain_pct = (surplus_kwh * charge_efficiency / usable_battery_kwh) * 100.0`
- `target_soc_raw = 100.0 - solar_soc_gain_pct + safety_margin_soc`
- `target_soc_pct = round(clamp(target_soc_raw, min_operational_soc, max_operational_soc))`
- `grid_energy_required_kwh = ((max(0.0, target_soc_pct - current_soc_pct) / 100.0) * usable_battery_kwh) / effective_grid_efficiency`
- `charging_power_kw = (charging_current_a * nominal_voltage_v) / 1000.0`
- `estimated_duration_minutes = ceil((net_energy_kwh / charging_power_kw) * 60.0) + buffer_minutes`
- `recommended_start_at = max(window_start_at, window_end_at - timedelta(minutes=estimated_duration_minutes))`
- `forecast_error_kwh = actual_production_kwh - forecast_kwh`

## 3. Entidades implementadas

- `sensor` (en ES / EN mediante `translation_key`):
  - `pv_forecast_tomorrow` (Previsión FV mañana, `kWh`)
  - `load_forecast_tomorrow` (Consumo diurno previsto mañana, `kWh` + traza `samples_used` / `samples_discarded`)
  - `surplus_tomorrow` (Excedente solar previsto mañana, `kWh`)
  - `target_soc` (SOC objetivo a las 08:00, `%` + atributos `target_soc_raw`, `is_frozen`, `was_clamped`, etc.)
  - `grid_energy_required` (Energía de red simulada necesaria, `kWh`)
  - `recommended_charge_start` (Hora de inicio de carga recomendada, `timestamp`)
  - `forecast_error` (Error de previsión FV, `kWh`, categoría diagnóstico)
  - `model_status` (Estado del modelo, `enum`, categoría diagnóstico + `solar_window_paused` y `last_control_*`)
- `binary_sensor`:
  - `calculation_ready` (Cálculo listo, categoría diagnóstico)
- `switch`:
  - `real_control` (Control real del inversor, categoría configuración, **OFF por defecto**)

## 4. Control del Deye (`control.py`)

- Adaptador `InverterController` intercambiable:
  - `ReadOnlySimulationController`: activo cuando `real_control` está en `OFF`.
  - `DeyeProgramSocController`: activo solo cuando `real_control` está en `ON` y `deye_program_soc_entity` está configurada.
- Comportamiento seguro:
  - Mantiene `night_idle_soc` (`20 %`) fuera de `00:00–08:00` y dentro de la ventana antes de `recommended_start_at`.
  - Escribe `target_soc_pct` en `number.inversordeye_program_1_soc` cuando `should_charge_now = True` y verifica la lectura tras 2 segundos.
  - Si `Cálculo listo` es `False` o la entidad destino no está disponible, no ordena carga (`fail_safe_hold`).
  - Nunca modifica tensiones, corrientes máximas, límites BMS ni protecciones de red.

## 5. Pruebas (`tests/unit/`)

36 pruebas unitarias ejecutadas con `unittest` (`test_calculator.py`, `test_estimator.py`, `test_schedule.py`, `test_charge_plan.py`, `test_history_and_control.py`, `test_control_and_forecast.py`) cubriendo fórmulas, redondeo/clamp, histórico insuficiente, ventana `Sun`, pausa solar, cálculo de hora de inicio, error de previsión y decisiones fail-safe.
