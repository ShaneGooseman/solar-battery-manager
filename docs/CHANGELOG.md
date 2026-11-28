# Changelog

Todos los cambios relevantes de **Solar Battery Manager** se documentan en este archivo.

## [0.2.8] — 2026-11-28
- Asocia las entradas del **Logbook** de control real al `entity_id` del interruptor `Control real del inversor`, de modo que los cambios automáticos del SOC aparecen directamente en la tarjeta **Actividad** del dispositivo.
- Renombra la etiqueta de `battery_nominal_voltage` en la interfaz a **Voltaje de carga de la batería (V)** / **Battery charging voltage (V)** con descripción aclaratoria (manteniendo compatibilidad con configuraciones existentes).

## [0.2.7] — 2026-11-26
- Usa `suggested_value` en los selectores de entidades opcionales de `ConfigFlow` y `OptionsFlow` para evitar errores con `default=None` y permitir limpiar campos opcionales en la UI.
- Reporta explícitamente el motivo cuando el sensor de consumo diario no tiene unidad `kWh`/`Wh` en lugar de enmascararlo como `INSUFFICIENT_HISTORY`.
- Auto-desactiva `Control real del inversor` con `WARNING` si se elimina la entidad destino del Deye en Opciones.
- Cambia el título de nuevas entradas a `Solar Battery Manager`.

## [0.2.6] — 2026-11-26
- **Auditoría limpia (Logbook + Store)**: persiste en `Store` las últimas 20 acciones reales (`action_history`) y emite eventos en el **Logbook** únicamente cuando cambia el valor escrito o se produce un error deduplicado (evitando 288 entradas/día). Añade `after_dependencies: ["logbook"]` en `manifest.json`.
- **Validación de unidades flexible**: `ConfigFlow` y `OptionsFlow` permiten `unit_of_measurement` ausente en entidades `number` opcionales de Deye/corriente, rechazando únicamente unidades incompatibles.
- **Motivos de frescura**: propaga `stale_state` del SOC de batería al motivo de `ChargeSchedulePlan`.
- **Tests y documentación**: test real del clamp tras redondeo entero (`was_clamped=True`) y sincronización de `TECHNICAL_SPEC.md`, `README.md` y `README.en.md`.

## [0.2.5] — 2026-11-26
- **Seguridad al desactivar el switch**: desactiva y persiste `real_control_enabled = False` antes de restaurar `night_idle_soc` en `try/except`, evitando que un fallo del inversor bloquee el apagado del control real.
- **Aislamiento de fallos**: encapsula consultas al `recorder` y llamadas de escritura al inversor en `try/except` para no tumbar el coordinador ni el switch.
- **Captura de producción diaria**: elimina el fallback basado en `freeze` para evitar capturar `0.0` si el freeze es posterior a medianoche.
- **Validación de entidades en UI**: comprueba unidades esperadas (`kWh`/`Wh`, `%`, `A`) en `ConfigFlow` y `OptionsFlow`.
- **Auditoría y frescura**: registra escrituras reales en el **Logbook** de Home Assistant y `action_history` en diagnósticos; amplía ventanas de frescura a `36 h` (previsión FV) y `60 min` (SOC), propaga motivos `stale_state`, y actualiza `was_clamped` tras el redondeo entero.
- **Documentación**: añade requisitos del inversor Deye/Solarman y guía de solución de problemas en `README.md` y `README.en.md`.

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
