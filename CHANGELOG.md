# Changelog

Todos los cambios relevantes de **Solar Battery Manager** se documentan en este archivo.

## [0.2.4] — 2026-11-26
- Captura la producción fotovoltaica diaria una sola vez tras el atardecer (`solar_end`), evitando pérdidas en invierno cuando pasan más de 6 h hasta las `23:55` o si el freeze cae dentro de la ventana tarifaria.
- Amplía `MAX_PRODUCTION_AGE` a `24 h`.

## [0.2.3] — 2026-11-26
- Usa `last_reported` (con fallback a `last_updated`) para detección de datos obsoletos, evitando falsos positivos en entidades con valor estable.
- Exime de caducidad a ajustes estáticos como la corriente máxima de carga desde red (`grid_charge_current_entity`).
- Separa constantes de frescura (`MAX_PV_FORECAST_AGE`, `MAX_BATTERY_SOC_AGE`, `MAX_PRODUCTION_AGE`).
- Reduce la espera de verificación tras escritura en Deye a `5 s × 2 intentos`.
- Usa hora local al restaurar el SOC de reposo cuando se desactiva el interruptor de control real.
- Añade test automático de sincronización entre `const.VERSION` y `manifest.json`.

## [0.2.2] — 2026-11-26
- Corrige `diagnostics.py` (`entry.runtime_data` + `charge_plan`, `forecast_comparison` y `frozen_snapshots`).
- Añade *latch* (enclavamiento) persistido por noche para evitar oscilaciones (*chattering*) del `Program 1 SOC` durante la carga.
- Exige unidad explícita (`kWh` o `Wh`) y umbral de completitud ≥ 75 % en estadísticas horarias del Recorder.
- Valida `min_operational_soc <= night_idle_soc <= max_operational_soc`.
- Cachea por día las consultas SQL al Recorder.
- Cambia `Error de previsión FV` a comparación de día completo anterior y restaura `night_idle_soc` al desactivar el switch.

## [0.2.1] — 2026-11-25
- Pausa el recálculo de SOC y las consultas al Recorder durante la ventana solar (amanecer–atardecer).

## [0.2.0] — 2026-11-25
- Añade interruptor opt-in `Control real del inversor` (apagado por defecto) para gestionar `Program 1 SOC` del Deye.
- Añade el sensor diagnóstico `Error de previsión FV`.

## [0.1.3] – [0.1.5] — 2026-11-25
- Cálculo de `Hora de inicio de carga recomendada` según amperaje máximo y tensión nominal.
- Soporte multiidioma completo (Español / Inglés) para entidades, estados y formularios.
- Integración obligatoria con `Sun` (`sun.sun`) para obtener amanecer y atardecer automáticamente.

## [0.1.0] – [0.1.2] — 2026-11-25
- Lanzamiento inicial en modo simulación de solo lectura, motor puro desacoplado, compatibilidad HACS, dispositivo de servicio e icono local.
