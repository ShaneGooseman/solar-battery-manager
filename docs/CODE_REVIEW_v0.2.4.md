# Revisión de código — Solar Battery Manager v0.2.4

| | |
|---|---|
| **Fecha** | 2026-11-26 |
| **Alcance** | Integración completa (`custom_components/solar_battery_manager/`), tests, documentación y metadatos del repositorio |
| **Commit revisado** | `d1ca6a4` (HEAD): v0.2.4 + reorganización de documentación + licencia MIT |
| **Método** | Lectura completa del código, 40 tests unitarios, compilación, validación de JSON/traducciones, simulaciones con el motor real y contraste con el código de Home Assistant |
| **Estado del árbol** | Limpio, sin cambios locales |

> Revisión completa e independiente. Sustituye al informe de la v0.2.2 (`docs/CODE_REVIEW_v0.2.2.md`) como estado actual del proyecto; al final se incluye la trazabilidad de los hallazgos anteriores.

---

## Veredicto

La integración está **madura para simulación**: arquitectura limpia, motor puro y bien probado, fallo seguro ante datos inválidos, persistencia robusta y documentación ya sincronizada. Los 40 tests pasan y el flujo principal (objetivo, congelación, *latch*, captura de producción) es coherente.

Para **control real** quedan riesgos que conviene cerrar antes de activarlo:

1. La desactivación del switch puede fallar si la escritura al inversor lanza una excepción (A1).
2. Un error del `recorder` o del servicio de escritura tumba todo el coordinador, incluido el propio switch (A2).
3. No está documentado ni validado el prerrequisito del inversor (programa TOU/grid-charge del Deye) del que dependen las escrituras (A3).
4. La selección de entidades no valida unidades ni dominio funcional; una elección errónea puede escribir en un ajuste equivocado (A4).
5. Queda un fallo de captura de producción con `freeze` posterior a medianoche (M1) y el objetivo puede incumplirse en silencio si la potencia real es menor que la planificada (M3).

**Recomendación:** mantener el control real desactivado hasta resolver A1–A4 y añadir tests de la capa HA.

---

## 1. Arquitectura y fundamentos

Puntos sólidos, verificados en esta revisión:

- **Separación real** entre motor puro (`engine/`), coordinación (`coordinator.py`), persistencia (`Store`) y control (`control.py`, protocolo `InverterController`). El motor no importa Home Assistant y se prueba sin él.
- **Fallo seguro** consistente: previsión o SOC inválidos/obsoletos, histórico insuficiente, corriente inválida o entidad destino no disponible llevan a `fail_safe_hold`, nunca a ordenar carga.
- **Idempotencia y anti-chattering**: el *latch* persistido evita las oscilaciones del Program SOC (verificado: de 20 escrituras a 1).
- **Persistencia pensada**: objetivo congelado por fecha, `latched_night_date`, `actual_pv_by_date`, recorte a 7 días y compatibilidad con el formato v0.1.
- **Patrones HA correctos**: `config_entry=entry`, `entry.runtime_data`, `_async_setup`, `async_config_entry_first_refresh`, `CoordinatorEntity`, `DeviceInfo` de servicio, `brand/` con iconos, traducciones completas.
- **Calidad de repositorio**: 40 tests, CI con `unittest` + `hassfest` + HACS, `CHANGELOG`, `LICENSE` MIT, sin dependencias externas, `iot_class: calculated`.
- **Documentación**: README, spec y changelog coherentes con v0.2.4; `PROJECT_BRIEF` marcado como histórico.

---

## 2. Hallazgos

### 2.1. Altos

#### A1 — Desactivar el control real puede fallar si la escritura al inversor lanza una excepción

[`coordinator.py:260-282`](../custom_components/solar_battery_manager/coordinator.py#L260-L282): al apagar el switch se escribe primero el SOC de reposo y **después** se pone `_real_control_enabled = False`. Si `async_apply_program_soc` lanza (por ejemplo, el servicio `number.set_value` falla porque la entidad desapareció o la integración Deye está caída), la excepción sale de `async_turn_off`, el flag sigue en `True` y **el usuario no puede desactivar el control real** justo cuando el inversor está fallando.

**Impacto:** seguridad. La única vía de desactivación queda bloqueada por el mismo fallo que motiva desactivar.

**Arreglo:** invertir el orden y aislar la escritura:

```python
if self._real_control_enabled and target_entity:
    self._real_control_enabled = False       # desactivar siempre
    await self._async_save_storage()
    try:
        await controller.async_apply_program_soc(...)  # best-effort
    except Exception:                        # noqa: BLE001
        _LOGGER.exception("No se pudo restaurar el SOC de reposo al desactivar")
```

#### A2 — Un error del Recorder o del servicio de escritura tumba todo el coordinador

No hay `try/except` alrededor de las dos llamadas externas de `_async_update_data`:

- [`coordinator.py:555-579`](../custom_components/solar_battery_manager/coordinator.py#L555-L579): `async_fetch_daytime_load_history` (consulta SQLite del `recorder`).
- [`coordinator.py:682-687`](../custom_components/solar_battery_manager/coordinator.py#L682-L687): `controller.async_apply_program_soc` (servicio `number.set_value`).

Cualquier `SQLAlchemyError`, base de datos bloqueada, disco lleno o fallo del servicio propaga la excepción fuera de `_async_update_data`: el coordinador registra *"Unexpected error fetching..."*, marca `last_update_success = False` y **todas las entidades quedan no disponibles**, incluido el switch de control real. El fallo de una consulta histórica no debería invalidar el objetivo ni impedir apagar el control.

**Arreglo:** encapsular el histórico en `try/except` y degradar a "histórico insuficiente" (estado inválido + motivo, entidades disponibles); encapsular la escritura y registrar `write_failed` sin tumbar el ciclo.

#### A3 — Prerrequisito del inversor (TOU / grid-charge) no documentado ni validado

La integración escribe únicamente el SOC del Program 1 (`number.inversordeye_program_1_soc`) y asume que el inversor aplicará ese valor en la ventana `00:00–08:00`. En los Deye/Sunsynk, ese SOC forma parte del programa **Time of Use**: si el programa no está activo, si su franja horaria no coincide o si la carga desde red está deshabilitada, la escritura queda **inerte o se aplica en otra franja**.

Además, el plan asume que la corriente configurada es **de batería (DC)** y que la tensión nominal es `51,2 V`; el brief indica una batería de **48 V**. Con una corriente AC o una tensión distinta, `charging_power_kw` cambia y la hora de inicio se desvía.

**Impacto:** el control real puede no cargar cuando se espera, o hacerlo en una franja distinta, sin que la integración lo detecte (solo verifica la entidad `number`).

**Arreglo:** añadir a README/spec una sección "Requisitos del inversor" (Programa 1 activo, franja, grid charge, misma entidad de SOC, corriente en A de batería, tensión real del pack, `charging_power_kw` esperado para contraste) y, si es posible, comprobar el estado del programa o la potencia de carga real.

#### A4 — Selección de entidades sin validación funcional

[`config_flow.py:118-152`](../custom_components/solar_battery_manager/config_flow.py#L118-L152) acepta cualquier `sensor`/`number` del dominio:

- La entidad destino del Deye puede ser otro ajuste `number` cualquiera: la integración escribiría en él.
- La corriente puede ser una entidad que no represente la corriente de carga.
- La previsión puede ser "hoy" en lugar de "mañana", o una potencia en W en lugar de energía.
- El consumo puede no tener estadísticas de largo plazo y dejar la integración permanentemente en "histórico insuficiente".

**Impacto:** seguridad (escritura en un ajuste equivocado) y corrección (objetivo calculado con datos equivocados).

**Arreglo:** validar `unit_of_measurement`, `device_class`/`state_class`, existencia de estadísticas y, para el SOC del Deye, unidad `%`; al menos, mostrar advertencias claras en el formulario y una confirmación al activar el control real.

### 2.2. Medios

#### M1 — La captura de producción guarda `0.0` si el `freeze` cae después de medianoche y antes de la ventana

[`coordinator.py:484-494`](../custom_components/solar_battery_manager/coordinator.py#L484-L494):

```python
should_capture_pv = (
    solar_end is not None and local_t >= solar_end
) or (schedule_state.is_freeze_active and not schedule_state.in_tariff_window)
```

La condición principal (tras el atardecer) es correcta y arregla N9/N10. El **fallback** sigue basándose en el freeze: con una configuración admitida como `freeze 00:50` y ventana `01:00–08:00`, a las 00:55 se cumple `is_freeze_active and not in_tariff_window`, la producción de hoy es ~0 y se guarda bajo la fecha del nuevo día. Cuando llega el atardecer, `today_key` ya existe y **no se recaptura**: el día queda con 0 kWh y el sensor de error muestra `−previsión`.

Verificado con el motor y `evaluate_schedule`:

```text
--- freeze 00:50, ventana 01:00-08:00 ---
00:55  in_window=False freeze=True   should=True   captura=True  stored=0.0
17:50  in_window=False freeze=False  should=True   captura=False stored=0.0
resultado del día: 0.0
```

**Arreglo:** eliminar el fallback basado en el freeze y sustituirlo por una hora fija de tarde-noche (p. ej. `local_t >= 22:00`) o por "tras el atardecer y al menos N minutos después"; el caso de `sun` no disponible puede usar esa hora fija.

#### M2 — El control real persiste encendido tras reiniciar y activarlo escribe de inmediato

- [`coordinator.py:216-220`](../custom_components/solar_battery_manager/coordinator.py#L216-L220) restaura `real_control_enabled` del `Store`; tras un reinicio a las 03:00 la integración vuelve a escribir sin una acción explícita del usuario. Solo hay un `warning`.
- Activar el switch dispara un refresh que, fuera de la ventana, escribe `night_idle_soc` en el inversor sin confirmación previa ([`coordinator.py:280-282`](../custom_components/solar_battery_manager/coordinator.py#L280-L282)).

**Arreglo:** arrancar siempre en simulación y exigir re-armado, o al menos confirmación explícita y un aviso visible; documentar que encender el switch provoca una escritura inmediata.

#### M3 — El objetivo puede incumplirse en silencio si la potencia real es menor que la planificada

El plan usa la corriente máxima configurada y el *latch* evita oscilaciones, pero no hay realimentación con la potencia medida. Simulación con objetivo 60 %:

| Potencia real | Escrituras | SOC a las 08:00 |
|---|---|---|
| 1,00 kW | 1 | **55,6 %** |
| 1,28 kW (plan) | 1 | 60,0 % |
| 1,50 kW | 1 | 60,0 % |
| 2,56 kW | 1 | 60,0 % |

**Arreglo:** comprobar el progreso cerca del final de la ventana (si `SOC < objetivo` y quedan pocos minutos, avisar o adelantar el inicio en la siguiente planificación) o re-planificar con potencia real medida.

#### M4 — La pausa solar congela los sensores informativos entre ~9 h (invierno) y ~15 h (verano)

[`coordinator.py:496-521`](../custom_components/solar_battery_manager/coordinator.py#L496-L521): durante el día se devuelve el snapshot anterior, así que `pv_forecast_tomorrow`, `load_forecast_tomorrow`, `target_soc` y `recommended_charge_start` no se actualizan aunque el proveedor de previsión cambie; además `should_charge_now`/`can_reach_target_in_window` quedan obsoletos mientras `in_tariff_window` sí es fresco.

La caché diaria del Recorder ya elimina la parte cara; la pausa puede reducirse a "no escribir en el inversor" manteniendo el cálculo vivo.

#### M5 — La verificación de escritura comprueba la entidad de HA, no la carga real

[`control.py:159-188`](../custom_components/solar_battery_manager/control.py#L159-L188): hasta 5 s × 2 intentos comprobando `number.inversordeye_program_1_soc`. Eso demuestra que la entidad aceptó el valor, no que el inversor esté cargando (depende del TOU, de la corriente y del estado del equipo). Además bloquea el coordinador hasta 10 s.

**Arreglo:** documentar el alcance de la verificación y, opcionalmente, confirmar con potencia de batería o rampa de SOC; mover la espera fuera del ciclo del coordinador.

#### M6 — Ventanas de frescura ajustadas y motivos de descarte poco visibles

- SOC: 30 min usando `last_reported`/`last_updated`. Si la integración del SOC solo reporta al cambiar y la batería está estable, el plan puede quedar inválido y frenar el *latch*.
- Previsión: 24 h. Un proveedor que actualiza una vez al día y pierde una ejecución deja la noche sin objetivo (fail-safe correcto, pero conviene 30–36 h).
- Los motivos `stale_state` no llegan al plan ni a los atributos del sensor de objetivo: el usuario ve "previsión inválida" sin saber que era antigüedad.

**Arreglo:** ampliar/adaptar las ventanas, exponer el motivo concreto y registrar un `warning` una sola vez por entidad.

#### M7 — Sin auditoría persistida de acciones de control

Solo se conserva `last_action` en memoria y en diagnósticos; no hay `logbook` ni historial. AGENTS.md pide "registro de acciones" para el control real.

**Arreglo:** `logbook.async_log_entry` en cada escritura (o un buffer persistido de las últimas N acciones) con SOC, resultado y verificación.

### 2.3. Bajos

- **B1 — `yesterday_snapshot` sin guardia de tipo** ([`coordinator.py:410-415`](../custom_components/solar_battery_manager/coordinator.py#L410-L415)): `_restore_frozen_result` valida que el snapshot sea `dict`, pero la comparación hace `.get()` directamente; un storage corrupto lanzaría `AttributeError` y tumbaría el ciclo. Añadir `isinstance(..., dict)`.
- **B2 — Docstring y nombre obsoletos** ([`coordinator.py:386-393`](../custom_components/solar_battery_manager/coordinator.py#L386-L393)): `_capture_pv_at_freeze_and_compare_yesterday` dice "at pre-midnight freeze", pero ahora captura tras el atardecer. Renombrar a `_capture_daily_pv_and_compare_yesterday`.
- **B3 — `was_clamped` no refleja el clamp por redondeo entero** ([`calculator.py:165-169`](../custom_components/solar_battery_manager/engine/calculator.py#L165-L169)): si el bruto está dentro de `[min, max]` pero el redondeo cae fuera del rango entero (`ceil(min)`/`floor(max)`), el valor se ajusta sin marcar `was_clamped`. Atributo engañoso; corregir el flag o documentarlo.
- **B4 — Constantes muertas**: `CONF_SIMULATION_MODE` y `DEFAULT_SIMULATION_MODE` ([`const.py:42,61`](../custom_components/solar_battery_manager/const.py#L42)) no se usan desde que el modo se controla con el switch.
- **B5 — Ruido de logs**: `Grid charge current entity error` ([`coordinator.py:635-636`](../custom_components/solar_battery_manager/coordinator.py#L635-L636)) y `write_skipped_unavailable` se repiten cada 5 minutos si la entidad está mal configurada.
- **B6 — Conversión de unidades históricas**: `statistics_during_period` se llama con `units=None`; si el sensor cambió de unidad (Wh→kWh), los datos antiguos se escalan con la unidad actual. Pasar `units={entity_id: "kWh"}` deja la conversión en HA.
- **B7 — DST en el plan de carga**: `plan_charge_window` combina fecha/hora local con `ZoneInfo`; en el salto de primavera una hora de inicio anterior a las 03:00 puede ser una hora local inexistente y mostrarse de forma confusa (la comparación absoluta sigue siendo segura). Añadir un test del día de cambio.
- **B8 — Metadatos estáticos**: el dispositivo muestra siempre `model="Simulation Mode (Read-Only)"` ([`sensor.py:242-249`](../custom_components/solar_battery_manager/sensor.py#L242-L249) y homólogos) aunque el control real esté activo; y los nombres "SOC objetivo a las 08:00" quedan mal si se cambia la ventana tarifaria.
- **B9 — Tests de la capa HA**: no hay pruebas del coordinador (congelación, pausa, *latch*, captura, M1), del config flow ni de diagnósticos. `pytest` está configurado en `pyproject.toml` pero el CI usa `unittest`; tampoco hay lint/tipos.
- **B10 — Documentación**: la spec no describe el paso de captura tras el atardecer; el CHANGELOG afirma que se evita la pérdida "si el freeze cae dentro de la ventana tarifaria", cierto para el caso principal pero no para el `freeze` previo a la ventana tras medianoche (M1); falta una sección de troubleshooting con los estados (`stale_state`, `insufficient_history`, `incomplete_solar_window_hours`, `fail_safe_hold`).

---

## 3. Estado respecto a las revisiones anteriores

| Hallazgo previo | Estado en v0.2.4 |
|---|---|
| N1 — obsolescencia por `last_updated` | **Corregido** (`check_state_freshness` con `last_reported`) |
| N2 — captura con `max` y valor de ayer | **Corregido** (captura única; riesgo residual M1) |
| N3 — escritura del `Store` cada 5 min | **Corregido** |
| N4 — verificación de escritura | **Parcial** (10 s máx.; sigue verificando la entidad, M5) |
| N5 — timestamp al desactivar | **Corregido** |
| N6 — erratas de documentación | **Corregido** (nuevas notas en B10) |
| N7 — constantes de frescura | **Corregido** |
| N8 — detalles varios | **Parcial** (test de `VERSION`; siguen A4, B3, B4) |
| N9 — `MAX_PRODUCTION_AGE` de 6 h | **Corregido** (24 h y captura tras el atardecer) |
| N10 — freeze dentro de la ventana | **Corregido** para el caso principal; **M1** cubre el freeze previo tras medianoche |
| Persistencia del control real / escritura al activar | **Abierto** (M2) |
| Infravaloración del objetivo si la potencia real es menor | **Abierto** (M3) |
| Validación de entidades | **Abierto** (A4) |
| Logbook / auditoría | **Abierto** (M7) |

---

## 4. Plan recomendado

1. **P0 — A1/A2 (seguridad y robustez):** desactivar antes de escribir y aislar escritura; encapsular histórico y escritura para que un fallo externo no tumbe el coordinador.
2. **P1 — A3/A4 (operación segura):** documentar y verificar el prerrequisito TOU/grid-charge, la semántica de la corriente y la tensión real; validar entidades en el config flow.
3. **P2 — M1/M2/M3:** corregir el fallback de captura, decidir el arranque en simulación y añadir comprobación de progreso del objetivo.
4. **P3 — M4/M5/M6:** reducir la pausa a "no escribir", sacar la espera del coordinador, ampliar/adaptar ventanas de frescura y exponer los motivos.
5. **P4 — M7/B1–B10:** logbook, guardias, limpieza, unidades, DST, nombres y tests de la capa HA con `pytest-homeassistant-custom-component`, más lint/tipos en CI.

---

## 5. Comprobaciones realizadas

- `python -m unittest discover -s tests/unit` → **40 tests OK** (incluye *latch*, obsolescencia, completitud y sincronía `VERSION`/manifest).
- `python -m compileall custom_components tests` → sin errores.
- JSON de `manifest`, `hacs`, `strings` y traducciones → válidos; ES/EN con las 111 claves de `strings.json`.
- Versiones sincronizadas: `const.VERSION` = `manifest.version` = README/SPEC/CHANGELOG = **0.2.4**.
- Simulación de la captura de producción para tres configuraciones de horario (por defecto, freeze previo a la ventana y freeze dentro de la ventana): confirma el caso correcto y **M1**.
- Simulación del *latch* (tabla de M3) y de `check_state_freshness` (reciente/viejo/`None`/naive/límite).
- Revisión de todos los archivos del repositorio: código, tests, documentación, CI, licencia e iconos de marca.

**Limitaciones:** no hay Home Assistant instalado en el entorno, así que no se ha podido validar en runtime (hassfest real, config flow en UI, estados de las entidades Deye, TOU del inversor). Las conclusiones sobre `last_reported`, `Store` y servicios se apoyan en el código de HA y en el comportamiento documentado de Deye/Sunsynk.
