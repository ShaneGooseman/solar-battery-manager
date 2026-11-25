# Verificación de la v0.2.5 — respuesta a la revisión de la v0.2.4

| | |
|---|---|
| **Fecha** | 2026-11-26 |
| **Commit verificado** | `88d2bbf` — «Blindar desactivación, aislar fallos externos y validar unidades en v0.2.5» |
| **Base comparada** | `docs/CODE_REVIEW_v0.2.4.md` (hallazgos A1–A4, M1–M7, B1–B10) |
| **Método** | Diff completo, lectura del código nuevo, 41 tests, compilación, JSON/traducciones, simulaciones con el motor real y contraste con el código de Home Assistant |
| **Estado del árbol** | Limpio |

> Antigravity afirma haber corregido lo solicitado. Esta verificación separa lo **realmente corregido**, lo **parcial** y lo que **sigue abierto**, y añade los problemas introducidos por la propia v0.2.5.

---

## Veredicto

Se han corregido de forma efectiva **A1, A2 y M1** (los tres hallazgos de mayor impacto), además de B1–B4 y parte de A4, M6, M7 y B8. La suite pasa de 40 a **41 tests** y las traducciones están completas.

Quedan abiertos **M2, M3, M4 y M5** (persistencia del control real y escritura al activar, objetivo no alcanzado, pausa solar y verificación a nivel de entidad), y **A3/A4 solo están resueltos parcialmente** (documentación sin validación y unidades sin `device_class`/estadísticas).

Además, la v0.2.5 introduce un problema nuevo relevante: **el Logbook recibe una entrada cada 5 minutos en modo control real** (288/día, ~105.000/año), y el test añadido para el arreglo de `was_clamped` **no ejercita el arreglo**.

---

## 1. Correcciones verificadas

| Hallazgo | Estado | Evidencia |
|---|---|---|
| **A1** Desactivar dependía de una escritura correcta | **Corregido** | [`coordinator.py:266-303`](../custom_components/solar_battery_manager/coordinator.py#L266-L303): apaga y persiste `False` antes de la escritura *best-effort* en `try/except` |
| **A2** Fallo del Recorder o del servicio tumbaba todo | **Corregido** | Consulta encapsulada ([`coordinator.py:616-640`](../custom_components/solar_battery_manager/coordinator.py#L616-L640)) y escritura encapsulada ([`coordinator.py:774-790`](../custom_components/solar_battery_manager/coordinator.py#L774-L790)); el coordinador sigue vivo y registra el motivo |
| **M1** Captura `0.0` con freeze previo tras medianoche | **Corregido** | Se elimina el fallback por freeze; captura con `solar_end` y, sin Sun, a partir de las 22:00 ([`coordinator.py:534-538`](../custom_components/solar_battery_manager/coordinator.py#L534-L538)). Simulación: freeze 00:50 → 00:55 no captura, 17:50 captura 8,5 |
| **B1** `yesterday_snapshot` sin guardia | **Corregido** | [`coordinator.py:456-460`](../custom_components/solar_battery_manager/coordinator.py#L456-L460) valida `isinstance(..., dict)` |
| **B2** Nombre/docstring de captura obsoletos | **Corregido** | Renombrado a `_capture_daily_pv_and_compare_yesterday` |
| **B3** `was_clamped` no reflejaba el clamp entero | **Corregido (código)** | [`calculator.py:166-176`](../custom_components/solar_battery_manager/engine/calculator.py#L166-L176) marca `was_clamped` y `clamp_bound`; el test añadido no lo comprueba (ver L5) |
| **B4** Constantes muertas | **Corregido** | Eliminadas `CONF_SIMULATION_MODE` y `DEFAULT_SIMULATION_MODE` |
| **A4** Validación de entidades | **Parcial** | [`config_flow.py:74-135`](../custom_components/solar_battery_manager/config_flow.py#L74-L135) valida existencia y unidades (`kWh`/`Wh`, `%`, `A`); no valida `device_class`, `state_class` ni estadísticas de largo plazo |
| **M6** Ventanas de frescura | **Parcial** | 36 h (previsión) y 60 min (SOC); el motivo `stale_state` se propaga para la previsión ([`coordinator.py:670-690`](../custom_components/solar_battery_manager/coordinator.py#L670-L690)), pero no para el SOC |
| **M7** Auditoría | **Parcial** | `action_history` + evento de Logbook ([`coordinator.py:407-432`](../custom_components/solar_battery_manager/coordinator.py#L407-L432)); sin persistencia propia y con volumen excesivo (L1) |
| **B8** Modelo del dispositivo | **Parcial** | Cambiado a «Adaptive Night Charge Controller»; los nombres «08:00» siguen fijos |
| **A3** Prerrequisito TOU del inversor | **Parcial** | README añade requisitos y troubleshooting; la spec no, y las entidades `select.*` no están verificadas (L4) |
| **Documentación general** | **Parcial** | README y CHANGELOG actualizados; la especificación técnica sigue con 24 h/30 min y sin requisitos ni auditoría (L3) |

---

## 2. Hallazgos que siguen abiertos

| Hallazgo | Situación |
|---|---|
| **M2** Control real persistido + escritura al activar | Sin cambios: `async_load_storage` restaura `real_control_enabled` (solo warning) y activar el switch provoca una escritura inmediata de `night_idle_soc` sin confirmación |
| **M3** Objetivo no alcanzado si la potencia real es menor | Sin cambios: no hay comprobación de progreso ni realimentación con potencia medida; sigue el 55,6 % con 1,0 kW |
| **M4** Pausa solar congela sensores | Sin cambios: `pv_forecast_tomorrow`, consumo, objetivo y plan siguen congelados entre ~9 h y ~15 h |
| **M5** Verificación a nivel de entidad | Sin cambios: 5 s × 2 comprobando que la entidad de HA reflejó el valor, no que el inversor esté cargando |
| **B5** Ruido de logs | Sigue el `warning` de la entidad de corriente cada 5 min; ahora se suma el volumen del Logbook |
| **B6** Unidades históricas | `statistics_during_period` sigue con `units=None` |
| **B7** DST en el plan de carga | Sin cambios ni test del día de cambio |
| **B9** Tests de capa HA y lint | Siguen sin tests de coordinador/config flow/diagnósticos ni lint/tipos; el único test nuevo es débil (L5) |
| **B10** Documentación | La spec no refleja 36 h/60 min, logbook, requisitos ni troubleshooting |

---

## 3. Problemas nuevos de la v0.2.5

### L1 — El Logbook recibe una entrada cada 5 minutos en modo control real

[`coordinator.py:407-432`](../custom_components/solar_battery_manager/coordinator.py#L407-L432): `_record_audit_action` emite un evento de Logbook para **toda** acción no simulada, incluidas las de «ya está en el valor» (`restore_idle_soc`, `wait_idle_soc`, `apply_target_soc` cuando el `number` ya tiene el SOC). Como el coordinador se refresca cada 5 minutos, son **288 entradas/día** (~105.000/año) aunque no haya ningún cambio real. El Logbook y la base de datos del Recorder se llenan de ruido y la acción importante queda diluida.

**Arreglo:** emitir el evento solo cuando cambie la acción/objetivo o cuando la escritura sea real y verificada; guardar igualmente el historial acotado.

### L2 — `action_history` es en memoria, duplica acciones y no es una auditoría real

El buffer de 20 entradas incluye también las acciones simuladas, que se repiten cada 5 min; cubre solo ~100 minutos y se pierde al reiniciar. La auditoría persistente depende del Logbook, que a su vez depende de que el componente esté cargado (el `manifest.json` no declara `logbook` ni `after_dependencies`). Si el usuario no tiene Logbook activo, el `try/except … pass` silencia el fallo y no queda rastro.

**Arreglo:** persistir un anillo acotado en `Store` (solo cambios reales), declarar `after_dependencies: ["logbook"]` o documentar el requisito, y no silenciar el error sin dejar constancia.

### L3 — La especificación técnica se quedó atrás

`docs/TECHNICAL_SPEC.md:55` sigue indicando **24 h / 30 min**, mientras el código, el README y el CHANGELOG ya usan **36 h / 60 min**. Tampoco recoge la auditoría, los requisitos del inversor ni el aislamiento de fallos que el README sí documenta.

### L4 — Entidades Deye documentadas sin verificar

El README presenta como requisito `select.inversordeye_time_of_use` y `select.inversordeye_battery_operation_mode`, que **no aparecen en la lista de entidades confirmadas** de `docs/PROJECT_BRIEF.md` (solo hay sensores). AGENTS.md prohíbe inventar entidades; si los nombres o los valores (`Week`, `Capacity`) no coinciden con la instalación, el usuario seguirá una guía incorrecta. Hay que verificarlos o marcarlos como «comprobar en tu instalación».

### L5 — El test nuevo no prueba el arreglo que dice cubrir

`test_rounding_past_fractional_bound_marks_was_clamped` usa `min_operational_soc=19.6` y un bruto de `19.6`, que redondea a `20` sin necesidad del nuevo clamp; solo comprueba `target_soc_pct == 20` y **no comprueba `was_clamped`**. El test pasaría igual sin la corrección. El escenario que sí la ejercita es, por ejemplo, `min=19.4` con bruto `19.4` (redondea a 19 y se eleva a 20): ahí `was_clamped` debe ser `True`.

### L6 — La validación de unidades puede bloquear el guardado de opciones

La comprobación exige `%` para el `Program 1 SOC` y `A` para la corriente. Si en esta instalación esas entidades `number` no exponen `unit_of_measurement` (algunas integraciones no lo hacen), el Options Flow **no dejará guardar** aunque el control real funcione. Conviene verificar las unidades reales antes de actualizar y, para entidades opcionales, degradar a advertencia en lugar de error.

### L7 — El README atribuye al coordinador una validación que no hace

Dice que «tanto el configurador como el coordinador validan … `A` para corriente». El coordinador solo valida unidades de energía para el histórico; la unidad de corriente y la de SOC solo se comprueban en el config flow.

---

## 4. Evidencias de las comprobaciones

### 4.1. Captura de producción (M1)

```text
--- Por defecto (freeze 23:55, ventana 00:00-08:00) ---
17:50  should=True   captura=True   stored=8.5
--- Freeze previo tras medianoche (00:50, ventana 01:00-08:00) ---
00:55  should=False  captura=False  stored=None
17:50  should=True   captura=True   stored=8.5
--- Freeze previo, sin Sun ---
00:55  should=False  captura=False  stored=None
22:30  should=True   captura=True   stored=8.5
```

### 4.2. Test de `was_clamped`

```text
escenario del nuevo test -> target: 20 | raw: 19.6 | was_clamped: False | clamp_bound: None
clamp por redondeo (min=19.4) -> target: 20 | raw: 13.933 | was_clamped: True | clamp_bound: min
```

El primer caso no ejerce el nuevo clamp; el segundo sí, pero no está en el test.

### 4.3. Volumen de auditoría

```text
refrescos/día: 288
eventos de Logbook/día en modo real: 288
entradas de action_history: 20 (cubren 100 minutos)
```

---

## 5. Comprobaciones ejecutadas

- `python -m unittest discover -s tests/unit` → **41 tests OK** (incluye el nuevo test, que pasa pero no cubre L5).
- `python -m compileall custom_components tests` → sin errores.
- JSON de manifest/HACS/strings y traducciones → válidos; **114 claves** en `strings.json` y sin diferencias en ES/EN.
- Versiones: `const.VERSION` = `manifest.version` = README/CHANGELOG = **0.2.5**; la spec también en el título, pero su línea de frescura está desactualizada (L3).
- Simulación de captura con tres configuraciones de horario (M1 verificado).
- Análisis del test de `was_clamped` y del volumen de Logbook.
- Contraste de `async_log_entry` con el código de HA: es un `@callback` que emite `EVENT_LOGBOOK_ENTRY`, por lo que la llamada es correcta; el problema es la frecuencia, no la API.

**Limitaciones:** sin Home Assistant en el entorno no se puede validar el Options Flow real, las unidades efectivas de las entidades Deye ni el TOU del inversor. Las conclusiones sobre la API de Logbook y `Store` se apoyan en el código de HA.

---

## 6. Recomendación

1. **P0:** corregir el volumen del Logbook (L1) y persistir una auditoría real (L2); decidir si se declara `logbook` como dependencia.
2. **P1:** verificar las entidades/unidades reales antes de la validación estricta (L6, L4) y alinear la spec (L3).
3. **P2:** cerrar M2–M5, que siguen abiertos desde la v0.2.4.
4. **P3:** sustituir el test débil (L5) por uno que compruebe `was_clamped`, y añadir tests de la capa HA y lint/tipos.
