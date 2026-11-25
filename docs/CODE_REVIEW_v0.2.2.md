# Revisión de código — Solar Battery Manager v0.2.2

| | |
|---|---|
| **Fecha** | 2026-11-26 |
| **Alcance** | `custom_components/solar_battery_manager/`, `tests/unit/`, `README*.md`, `docs/` |
| **Commits revisados** | `2856d60` (sincronización de documentación) y `f7e148b` (correcciones v0.2.2), sobre la base `9c45f2e` (v0.2.1) |
| **Diff** | 18 archivos, +547 / −335 líneas |
| **Método** | Lectura completa del código, ejecución de la suite de tests, compilación, simulaciones con el motor puro del propio proyecto y contraste con el código de Home Assistant |
| **Estado del árbol** | Limpio (sin cambios locales) |

> Este informe evalúa la v0.2.2 **respecto al informe anterior de la v0.2.1**. El informe previo tenía 17 hallazgos numerados; aquí se indica el estado de cada uno y se documentan los problemas nuevos introducidos por las correcciones.
>
> **Actualización (2026-11-26):** la v0.2.3 (`27fbb50`) corrige N1–N8. La verificación posterior está en la sección [Actualización v0.2.3](#actualización-v023--verificación-posterior), a continuación del veredicto.

---

## Veredicto

De los 17 hallazgos anteriores: **7 corregidos, 8 parcialmente corregidos y 2 siguen abiertos**.

La corrección del *chattering* del Program SOC funciona (verificado con simulación: de 20 escrituras a 1). Sin embargo, la solución de datos obsoletos introduce una **regresión crítica** que puede impedir por completo la carga desde red en modo de control real (N1), y el nuevo registro de producción diaria tiene un fallo en el cambio de medianoche (N2). El resto de hallazgos nuevos son de severidad media o baja.

**Recomendación (v0.2.2):** no activar el control real (`Control real del inversor`) hasta corregir N1 y N2. *Actualizado en v0.2.3: N1 y N2 corregidos; ver la sección siguiente.*

---

## Actualización v0.2.3 — verificación posterior

> Commit `27fbb50` («Corregir N1-N8 de revisión v0.2.2 y publicar v0.2.3»). Comprobaciones repetidas el 2026-11-26: **40 tests OK**, compilación OK, JSON y traducciones OK, versiones sincronizadas.

| Hallazgo | Estado en v0.2.3 | Verificación |
|---|---|---|
| N1 — obsolescencia por `last_updated` | **Corregido** | Nuevo `check_state_freshness` (usa `last_reported`/`last_updated`); la corriente de carga se lee con `max_age=None` y solo registra un warning. Matriz de casos correcta: reciente/viejo/None/naive/límite |
| N2 — captura de producción con `max` | **Corregido, con riesgo nuevo** | Captura única en el freeze, sin `max`: en la simulación el 26/11 queda en 8,5 kWh (antes 11,9). Ver N9 y N10 |
| N3 — escritura del `Store` cada 5 min | **Corregido** | Solo se persiste cuando hay captura (freeze) |
| N4 — verificación de escritura | **Parcial** | 5 s × 2 intentos (10 s máximo); sigue verificando la entidad de HA, no el inversor |
| N5 — timestamp de la escritura al desactivar | **Corregido** | Ahora usa hora local (`ZoneInfo`) |
| N6 — erratas de documentación | **Corregido** | v0.2.3 en README/SPEC/PLAN, *latch* y obsolescencia documentados, nota del modelo restaurada, sin "2 s" ni "36 pruebas" |
| N7 — constante única para tres semánticas | **Corregido** | `MAX_PRODUCTION_AGE` separada |
| N8 — detalles varios | **Parcial** | Test de sincronía `VERSION`/manifest; siguen el error genérico del config flow y el umbral del 75 % |

Comprobación de regresión del *latch* (motor sin cambios): 1 escritura y 60 % a las 08:00 con 1,28–2,56 kW; sigue sin alcanzarse el objetivo (55,6 %) si la potencia real es 1,0 kW, porque no hay realimentación con potencia medida.

### N9 — Medio: `MAX_PRODUCTION_AGE = 6 h` es más corto que el intervalo atardecer→freeze en invierno

La captura se hace en el freeze (23:55) y exige que la producción de hoy sea "fresca" según `last_reported`/`last_updated` con una ventana de 6 h. En Guardamar, el atardecer de finales de noviembre es ~17:50 y el freeze 23:55: **6 h 05 min**, por encima del límite. Si el integrador Deye solo escribe el estado cuando cambia (no re-reporta el mismo valor), la captura se rechaza; y como la ventana de captura se cierra a medianoche (`is_freeze_active and not in_tariff_window`), **ese día se pierde** y el sensor de error queda sin dato.

**Arreglo propuesto:** usar 24 h (o ninguna caducidad) para un contador diario que por diseño deja de cambiar al atardecer, y/o capturar en el primer refresco tras el atardecer en lugar de exigir frescura a las 23:55.

### N10 — Bajo: con el freeze dentro de la ventana tarifaria no se captura nunca

`should_capture_pv = is_freeze_active and not in_tariff_window`. Con una configuración admitida como freeze `00:50` y ventana `01:00–08:00`, durante el segmento de freeze ya se está dentro de la ventana, así que la condición nunca es cierta y la producción no se captura ningún día. **Arreglo propuesto:** desacoplar la captura del freeze; usar una hora fija pre-medianoche (23:55) o el primer refresco tras el atardecer.

---

## 1. Cambios revisados

La v0.2.2 responde al informe anterior con estos cambios principales:

- Diagnósticos corregidos y enriquecidos (snapshots congelados, plan de carga, comparación de previsión, estado del latch).
- *Latch* anti-chattering del SOC objetivo durante la ventana tarifaria, persistido en el `Store`.
- Detección de datos obsoletos por entidad, con ventanas de 24 h (previsión) y 30 min (SOC).
- Rechazo de unidades de energía desconocidas (antes, unidad ausente se asumía kWh).
- Umbral de completitud del 75 % para descartar días con histórico parcial.
- Comparación de previsión contra el día completo anterior, con registro del máximo diario de producción.
- Validación cruzada de `night_idle_soc` con el SOC mínimo/máximo operativo.
- Robustez del almacenamiento (snapshots corruptos ya no rompen el coordinador).
- Caché diaria de las consultas al Recorder.
- `entry.runtime_data` en lugar de `hass.data`, `config_entry=entry` explícito, `_async_setup` para cargar el storage, controlador Deye reutilizado y versión única (`VERSION`).

---

## 2. Seguimiento del informe anterior

| # | Hallazgo | Estado | Comentario |
|---|---|---|---|
| 1 | Diagnósticos rotos por `coordinator.controller` inexistente | **Corregido** | [`diagnostics.py:19-30`](../custom_components/solar_battery_manager/diagnostics.py#L19-L30) usa `runtime_data` y `real_control_enabled`, y añade snapshots, plan y comparación |
| 2 | *Chattering* del Program SOC cuando la potencia real difiere de la estimada | **Parcial** | El *latch* funciona (simulación: 20 → 1 escritura), pero sigue sin corregirse que el objetivo no se alcance si la potencia real es menor que la planificada |
| 3 | README/spec afirmaban "solo lectura" con control real implementado | **Corregido con erratas** | Ya describen el switch y el control opt-in, pero quedan datos falsos (N6) |
| 4 | El control real persiste encendido tras un reinicio | **Parcial** | Solo se añadió un *warning* ([`coordinator.py:216-220`](../custom_components/solar_battery_manager/coordinator.py#L216-L220)); sigue reanudando escrituras sin re-armado |
| 5 | Activar el switch escribe de inmediato `night_idle_soc` | **Abierto** | Sin cambios: activar fuerza un refresh que escribe el SOC de reposo |
| 6 | Desactivar el switch deja el Program SOC anterior activo en el inversor | **Corregido** | Escribe `restore_idle_on_disable` ([`coordinator.py:263-272`](../custom_components/solar_battery_manager/coordinator.py#L263-L272)); aparece un efecto secundario nuevo (N5) |
| 7 | No se detectaban datos obsoletos | **Implementado con fallo** | Mecanismo correcto en concepto, campo de fecha equivocado (N1) |
| 8 | Unidad ausente se interpretaba como kWh | **Corregido** | [`coordinator.py:123-129`](../custom_components/solar_battery_manager/coordinator.py#L123-L129) rechaza unidad desconocida |
| 9 | Sin validación de unidad/`device_class`/`state_class`/estadísticas | **Abierto** | El config flow sigue aceptando cualquier `sensor` |
| 10 | Días parciales contados como día completo | **Corregido** | Umbral del 75 % con motivo `incomplete_solar_window_hours` ([`history.py:132-173`](../custom_components/solar_battery_manager/history.py#L132-L173)) |
| 11 | Error de previsión comparaba día completo con producción parcial | **Concepto corregido** | Ahora compara el día anterior completo; nuevo fallo de captura (N2) |
| 12 | La pausa solar congela todos los sensores informativos | **Parcial** | Añadida caché diaria del Recorder (bien), pero la pausa sigue congelando previsión, consumo y plan |
| 13 | `night_idle_soc` podía quedar por debajo del SOC mínimo operativo | **Corregido** | [`config_flow.py:92-99`](../custom_components/solar_battery_manager/config_flow.py#L92-L99) |
| 14 | Verificación de escritura frágil (espera fija de 2 s) | **Parcial** | Espera + reintento, pero bloquea 2-20 s y sigue verificando la entidad de HA, no el inversor (N4) |
| 15 | Datos corruptos en storage podían romper el coordinador | **Corregido** | `try/except`, `int()` tolerante a floats y log del snapshot corrupto |
| 16 | Versión duplicada, tensión nominal discutible, nombres de entidad fijos | **Parcial** | `VERSION` unificada; tensión de 51,2 V y nombres "08:00" sin cambios |
| 17 | Sin tests de la capa HA ni lint/tipos en CI | **Parcial** | 38 tests (+2 de *latch* y completitud); sigue sin capa HA ni lint |

### 2.1. Confirmación del *latch* anti-chattering

Simulación con el motor actual (objetivo 60 %, batería 12 kWh, ventana 00:00–08:00, buffer 15 min, semántica Deye "carga mientras SOC < Program SOC"):

| Potencia real de carga | Escrituras sin *latch* | Escrituras con *latch* v0.2.2 | SOC a las 08:00 |
|---|---|---|---|
| 1,00 kW | 1 | 1 | **55,6 % (no llega al objetivo)** |
| 1,28 kW (planificada) | 1 | 1 | 60,0 % |
| 1,50 kW | 4 | **1** | 60,0 % |
| 2,00 kW | 14 | **1** | 60,0 % |
| 2,56 kW | 20 | **1** | 60,0 % |
| 3,00 kW | 22 | **1** | 60,0 % |

El *latch* elimina la oscilación, pero no la falta de realimentación: si la potencia real es inferior a la planificada, el objetivo se incumple en silencio (el buffer de 15 min solo cubre ~2,6 % de SOC).

---

## 3. Nuevos hallazgos de la v0.2.2

### N1 — Crítico: la detección de obsolescencia usa `last_updated`, que no cambia si el valor se repite

[`coordinator.py:105-112`](../custom_components/solar_battery_manager/coordinator.py#L105-L112) calcula la edad con `state_obj.last_updated`. En Home Assistant, `last_updated` solo avanza cuando cambia el estado o los atributos; las repeticiones solo actualizan `last_reported`. Es el campo correcto para medir "¿sigue vivo este dato?".

Se aplica a la **entidad de corriente máxima de carga** ([`coordinator.py:616-623`](../custom_components/solar_battery_manager/coordinator.py#L616-L623)), que es un ajuste estático y puede llevar días sin cambiar. A las 24 h se marca obsoleta, `charging_current_a = None`, el plan queda inválido y, dentro de la ventana, la decisión es `fail_safe_hold`: **no se ordena carga nunca**.

Consecuencia verificada con el motor puro:

```text
plan.is_valid = False | reason: charging_current_a must be a finite number > 0.
decision -> None fail_safe_hold | Charge plan invalid (...); refusing to order grid charge.
```

Con el *latch* ya activo el resultado es el mismo (`fail_safe_hold`), aunque en ese caso el inversor conserva el último objetivo escrito.

**Arreglo propuesto:**

1. Usar `last_reported` (o `max(last_reported, last_updated)`) como referencia de frescura.
2. No aplicar ventana de edad a entidades de configuración como la corriente de carga (o usar una ventana muy superior, p. ej. 7 días).
3. Propagar el motivo real (`stale_state:<entidad>`) al plan y a los atributos de diagnóstico en lugar del genérico "invalid current".

Afecta también a la previsión PV (24 h es ajustado para un proveedor que actualice una vez al día) y al SOC (30 min con `last_updated` puede dar falsos positivos cuando el SOC entero no cambia).

### N2 — Alto: la producción diaria se guarda con `max` y puede quedarse con el valor de ayer

[`coordinator.py:398-402`](../custom_components/solar_battery_manager/coordinator.py#L398-L402) guarda el máximo observado por fecha. Si el coordinador refresca justo después de medianoche, antes de que la integración Deye haya reiniciado `today_production` (o tras un reinicio de HA con estado restaurado), registra el total de ayer bajo la fecha de hoy. Al ser `max`, el valor ya no se corrige en todo el día y contamina el sensor `Error de previsión FV` del día siguiente.

Reproducción de la lógica:

```text
actual_pv_by_date: {'2026-11-25': 11.9, '2026-11-26': 11.9}
Producción atribuida al 26/11: 11.9 kWh  (real: 8.5)
```

**Arreglo propuesto:** detectar el reinicio diario (si el valor cae por debajo del máximo guardado, sobrescribir) o, preferible, **registrar la producción una sola vez en el freeze de las 23:55** y comparar con ese valor. Esta segunda opción elimina también N3.

### N3 — Medio: escritura del `Store` cada ~5 minutos durante el día

[`coordinator.py:465-466`](../custom_components/solar_battery_manager/coordinator.py#L465-L466) llama a `_async_save_storage()` cada vez que sube la producción de hoy. En HA, `Store.async_save` escribe inmediatamente (la variante diferida es `async_delay_save`), así que son ~120 escrituras/día innecesarias.

**Arreglo propuesto:** `async_delay_save` (10-15 min) o persistir solo en el freeze.

### N4 — Medio: la verificación bloquea el coordinador hasta 20 s y no verifica el inversor

[`control.py:159-188`](../custom_components/solar_battery_manager/control.py#L159-L188): 2 intentos × 10 esperas de 1 s, dentro de `_async_update_data`. Además, `number.set_value` actualiza el estado de la entidad en HA (posiblemente de forma optimista), por lo que releerla no demuestra que el Deye haya aceptado el valor; sigue sin confirmarse con potencia o SOC reales.

El README y la spec dicen "verifica 2 s después", que ya no es cierto.

**Arreglo propuesto:** timeout configurable y más corto, verificación contra una magnitud física (potencia de carga o rampa de SOC) y documentar el comportamiento real.

### N5 — Medio: desactivar el switch ahora escribe en el inversor

Es una mejora de seguridad (neutraliza el Program SOC), pero conviene documentarla: quien apaga el switch para "dejar de tocar el inversor" provoca una última escritura.

Además, esa acción usa `datetime.now(timezone.utc)` ([`coordinator.py:271`](../custom_components/solar_battery_manager/coordinator.py#L271)) mientras el resto de registros usan hora local, y su resultado no aparece en `last_action` ni en diagnósticos porque el siguiente refresh lo sustituye por la acción simulada.

### N6 — Bajo: erratas de documentación

- `docs/TECHNICAL_SPEC.md:1` y `docs/IMPLEMENTATION_PLAN.md:1` siguen indicando **v0.2.1**.
- `docs/IMPLEMENTATION_PLAN.md:9` y `docs/TECHNICAL_SPEC.md:57` dicen **36 pruebas** (hay 38).
- `README.md:71` y `docs/TECHNICAL_SPEC.md:51` dicen "verifica 2 s" (ahora hasta 20 s).
- `README.md:106` y `README.en.md:106` describen el error como "producción real **hoy**" cuando ahora es **ayer**.
- La reescritura de `docs/TECHNICAL_SPEC.md` eliminó la nota de que el modelo es simplificado y no garantiza alcanzar el 100 %; conviene recuperarla.
- No se documentan el *latch* ni las ventanas de obsolescencia.

### N7 — Bajo: una constante para tres semánticas

`MAX_PV_FORECAST_AGE` ([`const.py:12`](../custom_components/solar_battery_manager/const.py#L12)) se usa para previsión PV, producción de hoy y corriente de carga, que necesitan ventanas distintas. Separar en `MAX_PV_FORECAST_AGE`, `MAX_PRODUCTION_AGE` y `MAX_SETTING_AGE`.

### N8 — Bajo: detalles varios

- El error de validación de `night_idle_soc` es el genérico `invalid_parameters`; no indica qué campo falla.
- El umbral de completitud del 75 % puede rechazar días legítimos con huecos parciales y dejar el histórico por debajo del mínimo (el motivo sí se expone, lo cual es correcto).
- `VERSION` en `const.py` duplica la versión de `manifest.json` sin un test que las mantenga sincronizadas.

---

## 4. Hallazgos del informe anterior que siguen abiertos

- **Objetivo no alcanzado si la potencia real es menor que la planificada:** sin realimentación con potencia medida.
- **Activar el switch sigue escribiendo `night_idle_soc` de inmediato**, sin confirmación explícita.
- **Sin validación de entidad en el config flow:** unidad, `device_class`, `state_class` y existencia de estadísticas de largo plazo.
- **El switch sigue mostrando ON si la entidad Deye desaparece** (el controlador cae a simulación pero el estado no lo refleja).
- **Sin logbook ni auditoría persistida** de acciones de control (solo `last_action` en memoria).
- **Sin tests de la capa HA** (coordinador, config flow, diagnósticos, obsolescencia), justo donde están N1 y N2.
- **`datetime.now()` en lugar de `dt_util.utcnow()`**, lo que dificulta el test con reloj simulado.

---

## 5. Plan recomendado

1. **P0 — N1:** cambiar a `last_reported`, eximir o ampliar la ventana de la corriente de carga y propagar `stale_state` al plan y a los atributos. Añadir test unitario de la lógica extraída.
2. **P1 — N2/N3:** registrar la producción en el freeze (o detectar el reinicio diario) y persistir con `async_delay_save`. Test del caso medianoche.
3. **P2 — N6:** sincronizar versiones, "2 s", "hoy", recuperar la nota del modelo simplificado y documentar *latch* y obsolescencia.
4. **P3 — N4/N5:** timeout de verificación más corto y configurable, confirmación con potencia/SOC, documentar la escritura al desactivar y exponerla en `last_action`.
5. **P4 — pendientes:** validación de entidades en el config flow, confirmación al activar, fail-safe con neutralización, logbook y tests con `pytest-homeassistant-custom-component`.

---

## 6. Verificación realizada

- `python -m unittest discover -s tests/unit` → **38 tests OK** (antes 36).
- `python -m compileall custom_components tests` → sin errores.
- Simulación del bucle de decisión a 5 minutos con el motor real del proyecto (tabla de la sección 2.1).
- Simulación del efecto de `charging_current_a = None` sobre `plan_charge_window` + `decide_program_soc_action` (N1).
- Simulación de la captura de producción a medianoche con lógica `max` (N2).
- Contraste de `last_updated` / `last_reported` y de `Store.async_save` con el código fuente de Home Assistant.

**Limitaciones:** no hay Home Assistant instalado en el entorno de revisión, por lo que no se ha podido validar en runtime (hassfest, config flow real, estados reales de las entidades Deye). Las conclusiones sobre persistencia de estado y almacenamiento se apoyan en el código de HA, no en una ejecución completa.

---

## Anexo — Evidencias de simulación

### A.1. *Latch* anti-chattering

Reproducción del bucle del coordinador: cada 5 minutos se evalúa `evaluate_schedule` → `plan_charge_window` → *latch* si `should_charge_now` → `decide_program_soc_action(charge_latched=...)`, y se modela la carga como "mientras SOC < Program SOC, sube `P_real × Δt × η / capacidad`". Resultado en la tabla de la sección 2.1.

### A.2. Efecto de la corriente obsoleta (N1)

```text
plan.is_valid = False | reason: charging_current_a must be a finite number > 0.
decision -> None fail_safe_hold | Charge plan invalid (charging_current_a must be a
finite number > 0.); refusing to order grid charge.
con latch + plan inválido -> None fail_safe_hold
```

### A.3. Captura de producción a medianoche (N2)

```text
actual_pv_by_date: {'2026-11-25': 11.9, '2026-11-26': 11.9}
Producción atribuida al 26/11: 11.9 kWh  (real: 8.5)
```
