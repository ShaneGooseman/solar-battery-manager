# Solar Battery Manager

[🇬🇧 English documentation](docs/README.en.md) · [📋 Changelog](docs/CHANGELOG.md)

Integración personalizada para **Home Assistant Core (2026.11+)** que estima cuánta energía solar sobrará mañana y calcula el **SOC mínimo necesario al final de la tarifa económica nocturna** (por defecto `08:00`) para que la producción fotovoltaica del día lleve la batería al 100 %.

> **Seguridad por defecto (`v0.2.8`)**: la integración funciona en **modo simulación** mientras el interruptor **`Control real del inversor`** esté apagado (`OFF` por defecto). Si decides activarlo, únicamente ajusta el SOC objetivo del tramo horario nocturno (`number.inversordeye_program_1_soc`) sin modificar nunca tensiones, corrientes máximas ni protecciones del BMS.

---

## Cómo funciona a lo largo del día

1. **Día solar (amanecer → atardecer)**:
   - La integración mantiene el SOC de reposo nocturno (`20 %`) y pausa las consultas al `recorder` y el recálculo continuo mientras hay luz solar (`solar_window_paused: true`).
   - Tu inversor carga la batería con energía solar de forma normal.
2. **Atardecer**:
   - Captura una sola vez la producción fotovoltaica total del día (si configuraste el sensor de producción diaria) para poder calcular al día siguiente la precisión de la previsión.
   - Reanuda el cálculo de la noche siguiente usando el histórico diurno y la previsión FV de mañana.
3. **Congelación pre-medianoche (`23:55`)**:
   - Congela y guarda en almacenamiento persistente el **SOC objetivo a las 08:00** para que los reinicios diarios de sensores a medianoche o un reinicio de Home Assistant no alteren el plan de esa noche.
4. **Ventana económica nocturna (`00:00–08:00`)**:
   - **Antes de la hora recomendada de inicio**: mantiene el **SOC mínimo de reposo nocturno** (`20 %`), permitiendo que la vivienda descargue la batería durante la noche.
   - **Al llegar la hora recomendada** (calculada según el amperaje máximo de carga): aplica el **SOC objetivo** y queda **enclavada (*latch*)** hasta las `08:00` para evitar cortes u oscilaciones si la potencia real varía.
   - **A las `08:00`**: restaura el SOC de reposo (`20 %`).

---

## Cómo se calcula el SOC objetivo (fórmulas)

La integración **no** asume que la capacidad nominal de la batería sea la capacidad útil, ni resta el consumo total de 24 h (ya que el consumo nocturno puede cubrirse desde la red).

1. **Consumo diurno estimado (`consumo_diurno_kWh`)**:
   - Lee las estadísticas horarias del `recorder` únicamente entre **amanecer y atardecer** (según `sun.sun`) de los últimos *N* días (`14` por defecto).
   - Descarta días incompletos (`< 75 %` de horas válidas) o con valores inválidos; requiere al menos `3` días válidos.
   - Aplica **`Mediana`** *(por defecto, resistente a picos)* o **`Media`**.

2. **Excedente solar diurno estimado (`excedente_kWh`)**:
```text
excedente_kWh = max(0, prevision_FV_manana_kWh - consumo_diurno_kWh)
```

3. **Ganancia de SOC aportada por el sol (`ganancia_SOC_%`)**:
```text
ganancia_SOC_% = (excedente_kWh * eficiencia_carga / capacidad_util_kWh) * 100
```

4. **SOC objetivo al final de la ventana económica**:
```text
SOC_bruto_%    = 100 - ganancia_SOC_% + margen_seguridad_%
SOC_objetivo_% = round(min(SOC_max_operativo, max(SOC_min_operativo, SOC_bruto_%)))
```

5. **Energía de red simulada y hora de inicio recomendada**:
```text
delta_SOC         = max(0, SOC_objetivo_% - SOC_actual_%)
energia_red_kWh   = ((delta_SOC / 100) * capacidad_util_kWh) / eficiencia_carga
potencia_carga_kW = (corriente_max_red_A * tension_nominal_V) / 1000
energia_neta_kWh  = (delta_SOC / 100) * capacidad_util_kWh
duracion_min      = ceil((energia_neta_kWh / potencia_carga_kW) * 60) + margen_tiempo_min
hora_inicio       = max(inicio_tarifa, fin_tarifa - duracion_min)
```

> **Nota**: es un modelo energético simplificado; no garantiza alcanzar el 100 % si hay límites de potencia del inversor/BMS o desviaciones importantes de la previsión FV.

---

### Ejemplo numérico paso a paso

Con previsión FV de `11,91 kWh`, consumo diurno de `5,10 kWh`, `12,0 kWh` útiles, `90 %` de eficiencia, `5 %` de margen, SOC actual `40 %` y carga a `25 A @ 51,2 V` (`15 min` de margen de tiempo):

1. **Excedente**: `max(0, 11,91 - 5,10) = 6,81 kWh`
2. **Ganancia solar**: `(6,81 * 0,90 / 12,0) * 100 = 51,08 %`
3. **SOC objetivo**: `100 - 51,08 + 5 = 53,92 -> 54 %`
4. **Plan de carga** (`delta_SOC = 54 - 40 = 14 %`):
   - Energía neta: `1,68 kWh` | Energía de red estimada: `1,87 kWh`
   - Potencia: `25 * 51,2 / 1000 = 1,28 kW`
   - Duración: `ceil((1,68 / 1,28) * 60) + 15 = 94 min` → **Inicio recomendado: `06:26`**

---

## Entidades creadas

| Entidad | Tipo | Descripción |
| :--- | :--- | :--- |
| `Previsión FV mañana` | `sensor` (`kWh`) | Previsión fotovoltaica normalizada a kWh |
| `Consumo diurno previsto mañana` | `sensor` (`kWh`) | Consumo diurno estimado + traza de días usados/descartados |
| `Excedente solar previsto mañana` | `sensor` (`kWh`) | Excedente solar diurno estimado |
| `SOC objetivo a las 08:00` | `sensor` (`%`) | SOC objetivo calculado + atributos de trazabilidad y congelación |
| `Energía de red simulada necesaria` | `sensor` (`kWh`) | Energía teórica necesaria desde red respecto al SOC actual |
| `Hora de inicio de carga recomendada` | `sensor` (`timestamp`) | Hora calculada para iniciar carga según amperaje máximo |
| `Error de previsión FV` | `sensor` (`kWh`) | Diferencia entre producción total de ayer y previsión congelada para ayer |
| `Estado del modelo` | `sensor` (`enum`) | Estado del cálculo, pausa solar, *latch* y última acción de control |
| `Cálculo listo` | `binary_sensor` | Indica si el cálculo actual es válido y utilizable |
| `Control real del inversor` | `switch` | Interruptor opt-in para habilitar escritura en Program 1 SOC (`OFF` por defecto) |

---

## Seguridad y fallo seguro

- **Validación de frescura (`last_reported`)**: si la previsión FV lleva > `36 h` sin reportarse o el SOC > `60 min`, el cálculo pasa a inválido y **no ordena carga** (`fail_safe_hold`). La corriente máxima de carga (ajuste estático) no caduca por falta de cambios.
- **Unidades explícitas**: el configurador exige `kWh`/`Wh` para energía, `%` para el sensor SOC y, si están informadas, `%` para el SOC del programa y `A` para la corriente máxima; el coordinador exige `kWh`/`Wh` en los sensores de energía y falla de forma segura si falta la unidad.
- **Aislamiento de fallos**: un error temporal del `recorder` o del servicio de escritura no bloquea el resto de entidades ni impide apagar el interruptor `Control real del inversor`.
- **Verificación de escritura y auditoría**: en modo control real, espera hasta `5 s × 2 intentos` comprobando que la entidad en HA reflejó el nuevo valor; persiste las últimas 20 escrituras/errores reales en `Store` y emite entradas en el **Logbook** únicamente cuando cambia el valor aplicado o se produce un fallo.
- **Al apagar el interruptor**: desactiva el control real de inmediato y restaura el SOC de reposo nocturno (`20 %`) como acción *best-effort* antes de volver a simulación.

---

## Requisitos del inversor (Deye / Solarman)

Comprueba en tu instalación Deye/Solarman que se cumplen estas condiciones para que el control sobre `number.inversordeye_program_1_soc` funcione según lo esperado:

1. **Time of Use activo**: el selector de *Time of Use* de tu inversor debe estar habilitado (p. ej. `Week` o `Enabled`, no `Disabled`).
2. **Franja coincidente**: `Program 1` debe cubrir la ventana económica nocturna (`00:00` → `Program 2 = 08:00`) con carga desde red (`Grid`) habilitada en ese tramo.
3. **Modo por capacidad**: el modo de operación de batería debe estar configurado por capacidad/SOC (`Capacity`), no solo por voltaje.
4. **Corriente y tensión**: la entidad de corriente máxima de carga desde red debe expresar corriente DC de batería en Amperios; para baterías LiFePO4 de 16 celdas ("48 V"), la tensión nominal típica es `51,2 V`.

---

## Solución de problemas

- **`insufficient_history`**: el sensor de consumo aún no tiene suficientes días válidos con ≥ 75 % de horas en la ventana solar (`sun.sun`), o el Recorder tuvo un fallo temporal. Revisa el atributo `samples_discarded` de `Consumo diurno previsto mañana`.
- **`invalid_sun_window`**: la entidad `sun.sun` no está disponible o carece de `next_rising`/`next_setting`.
- **`invalid_pv_forecast` / `stale_state`**: el sensor de previsión FV está `unknown`/`unavailable` o supera las `36 h` sin reportar datos.
- **`fail_safe_hold`**: dentro de la ventana nocturna, la integración detectó un dato inválido u obsoleto y se niega a ordenar carga por seguridad.

---

## Instalación mediante HACS

1. Abre **HACS → Integraciones → `⋮` → Repositorios personalizados**.
2. Añade `https://github.com/ShaneGooseman/solar-battery-manager` (categoría **Integración**).
3. Instala **Solar Battery Manager** y **reinicia Home Assistant**.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → Solar Battery Manager**.

---

## Pruebas unitarias y documentación técnica

```powershell
python -m unittest discover -s tests/unit -v
```
*(En Windows requiere `tzdata` para `ZoneInfo("Europe/Madrid")`.)*

- [docs/CHANGELOG.md](docs/CHANGELOG.md) — Historial de versiones.
- [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) — Especificación técnica actual.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Estado por fases.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — Contexto inicial de la instalación.
