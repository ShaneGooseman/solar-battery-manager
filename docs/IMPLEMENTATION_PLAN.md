# Plan de implementación — Estado actual (v0.2.1)

## Fase 0 — Inspección y decisiones (Completada)
- Confirmada versión base **Home Assistant Core 2026.11**.
- Confirmadas entidades reales de Solarman/Deye (`sensor.inversordeye_*`, `number.inversordeye_program_1_soc`, `number.inversordeye_battery_grid_charging_current`), previsión ML (`sensor.pv_forecast_total_tomorrow`) y `sun.sun`.
- Definida consulta al Recorder mediante `get_instance(hass).async_add_executor_job(statistics_during_period, ...)`.

## Fase 1 — Integración base y motor puro (Completada)
- Motor puro desacoplado en `custom_components/solar_battery_manager/engine/` + 36 pruebas unitarias en `tests/unit/`.
- Config Flow / Options Flow por UI, multiidioma (ES/EN), dispositivo de servicio, icono local y compatibilidad con HACS.

## Fase 2 — Persistencia, simulación y pausa solar (Completada)
- Congelación diaria pre-medianoche (`23:55`) persistida en `Store`.
- Cálculo de `Hora de inicio de carga recomendada` según amperaje máximo de carga.
- Sensor diagnóstico `Error de previsión FV` comparando producción real frente a previsión congelada.
- Pausa automática de recálculo y consultas al Recorder durante la ventana solar (amanecer–atardecer).

## Fase 3 — Validación en vivo (En curso)
- Observar varios días en modo simulación (`Control real del inversor = OFF`), comparando `Error de previsión FV` y ajustando capacidad útil, eficiencia y margen si es necesario.

## Fase 4 — Adaptador de control Deye opt-in (Implementado en v0.2.0, desactivado por defecto)
- Implementado `DeyeProgramSocController` + interruptor `Control real del inversor` (`OFF` por defecto).
- Mantiene `night_idle_soc` (`20 %`) hasta la hora recomendada de inicio, aplica `target_soc_pct` en `number.inversordeye_program_1_soc` con verificación tras escritura y restaura `20 %` al salir de la ventana.
- Activar el interruptor únicamente tras validar la Fase 3.
