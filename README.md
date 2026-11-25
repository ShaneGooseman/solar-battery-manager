# Solar Battery Manager

[🇬🇧 English documentation](README.en.md)

Integración personalizada para **Home Assistant Core (2026.11+)** que estima el excedente fotovoltaico diurno del día siguiente y calcula el **SOC objetivo mínimo** al finalizar la ventana económica nocturna (por defecto `00:00–08:00`) para que la producción solar pueda llevar la batería al 100 %.

> **Modo actual: Solo lectura y simulación (`v0.1.5`)**
> Esta versión **no escribe en el inversor** ni modifica parámetros de protección del BMS. Todos los cálculos y recomendaciones se exponen como sensores de solo lectura para validación.

---

## Cómo se calcula el SOC objetivo (transparencia total)

La integración **no** asume que la capacidad nominal de la batería sea la capacidad útil, ni usa el consumo total de 24 horas (ya que el consumo nocturno puede cubrirse desde la red). El cálculo sigue exactamente estos 8 pasos:

### 1. Ventana solar diurna (`Sun`)
A partir de la entidad `Sun` configurada (`sun.sun` por defecto), se obtienen las horas locales de **amanecer** (`next_rising`) y **atardecer** (`next_setting`).
- Si la entidad `Sun` no existe, está `unavailable` o carece de ambos atributos, el cálculo **falla de forma segura** (`Ventana solar (Sun) no válida`) y no inventa valores.

### 2. Estimación del consumo diurno (`consumo_diurno_kWh`)
Se consultan las estadísticas horarias a largo plazo del `recorder` de Home Assistant para el sensor de consumo configurado, sumando **únicamente las horas comprendidas entre el amanecer y el atardecer** de los últimos *N* días (`lookback_days`, por defecto 14).
- Se descartan días con datos ausentes o valores negativos/no finitos (todo queda registrado en los atributos `samples_used` y `samples_discarded`).
- Si hay menos días válidos que el mínimo exigido (`min_history_days`, por defecto 3), el cálculo falla de forma segura (`Histórico insuficiente`).
- Se aplica el método seleccionado:
  - **`Mediana`** *(por defecto)*: menos sensible a picos puntuales de electrodomésticos.
  - **`Media`**: media aritmética de los días válidos.

### 3. Excedente solar diurno estimado (`excedente_kWh`)
```text
excedente_kWh = max(0, prevision_FV_manana_kWh - consumo_diurno_kWh)
```

### 4. Ganancia de SOC aportada por el sol (`ganancia_SOC_%`)
```text
ganancia_SOC_% = (excedente_kWh * eficiencia_carga / capacidad_util_kWh) * 100
```

Donde:
- `capacidad_util_kWh` es la capacidad real utilizable configurada por el usuario (no el nominal).
- `eficiencia_carga` es la eficiencia de carga configurada (p. ej. `0,90` para `90 %`).

### 5. SOC objetivo al final de la ventana económica (`08:00`)
```text
SOC_bruto_%    = 100 - ganancia_SOC_% + margen_seguridad_%
SOC_objetivo_% = round(min(SOC_max_operativo, max(SOC_min_operativo, SOC_bruto_%)))
```

### 6. Energía de red simulada necesaria (`energia_red_kWh`)
```text
delta_SOC       = max(0, SOC_objetivo_% - SOC_actual_%)
energia_red_kWh = ((delta_SOC / 100) * capacidad_util_kWh) / eficiencia_carga
```

### 7. Hora de inicio de carga recomendada
A partir de la corriente máxima de carga desde red configurada (en A) y la tensión nominal de batería (por defecto `51,2 V`):

```text
potencia_carga_kW = (corriente_max_red_A * tension_nominal_V) / 1000
energia_neta_kWh  = (delta_SOC / 100) * capacidad_util_kWh
duracion_min      = ceil((energia_neta_kWh / potencia_carga_kW) * 60) + margen_tiempo_min
hora_inicio       = max(inicio_tarifa, fin_tarifa - duracion_min)
```

Si `duracion_min` supera la duración de la ventana económica, se fija el inicio al principio de la ventana (`00:00`) y se indica en los atributos (`can_reach_target_in_window: false`).

### 8. Congelación pre-medianoche
Al llegar la hora de congelación configurada (por defecto `23:55`), el **SOC objetivo** queda congelado y guardado en el almacenamiento interno de Home Assistant para toda la ventana nocturna (`00:00–08:00`), evitando que los reinicios diarios de sensores a las `00:00` o un reinicio de Home Assistant alteren el objetivo.

---

### Ejemplo numérico paso a paso

Supongamos:
- Previsión FV mañana: `11,91 kWh`
- Consumo diurno estimado (mediana): `5,10 kWh`
- Capacidad útil configurada: `12,0 kWh` | Eficiencia: `90 %` | Margen seguridad: `5 %`
- SOC actual: `60 %` | Corriente máx. red: `25 A` @ `51,2 V` | Margen tiempo: `15 min`

1. **Excedente**: `max(0, 11,91 - 5,10) = 6,81 kWh`
2. **Ganancia solar**: `(6,81 * 0,90 / 12,0) * 100 = 51,08 %`
3. **SOC objetivo**: `100 - 51,08 + 5 = 53,92 -> 54 %` *(si el SOC actual es 60 %, no requiere carga de red)*
4. Si el SOC actual fuese **40 %** (`delta_SOC = 14 %`):
   - Energía neta a añadir: `0,14 * 12,0 = 1,68 kWh`
   - Energía de red estimada: `1,68 / 0,90 = 1,87 kWh`
   - Potencia de carga: `25 * 51,2 / 1000 = 1,28 kW`
   - Duración: `ceil((1,68 / 1,28) * 60) + 15 = 79 + 15 = 94 min`
   - Hora de inicio recomendada (para terminar a las `08:00`): **`06:26`**

---

## Entidades creadas

| Entidad | Tipo | Descripción |
| :--- | :--- | :--- |
| `Previsión FV mañana` | `sensor` (`kWh`) | Previsión fotovoltaica normalizada a kWh |
| `Consumo diurno previsto mañana` | `sensor` (`kWh`) | Consumo diurno estimado + traza de muestras usadas/descartadas |
| `Excedente solar previsto mañana` | `sensor` (`kWh`) | Excedente solar diurno estimado |
| `SOC objetivo a las 08:00` | `sensor` (`%`) | SOC objetivo calculado + atributos de trazabilidad y congelación |
| `Energía de red simulada necesaria` | `sensor` (`kWh`) | Energía teórica necesaria desde red respecto al SOC actual |
| `Hora de inicio de carga recomendada` | `sensor` (`timestamp`) | Hora calculada para iniciar carga según amperaje máximo |
| `Estado del modelo` | `sensor` (`enum`) | Estado del cálculo (`Correcto`, `Histórico insuficiente`, etc.) |
| `Cálculo listo` | `binary_sensor` | Indica si el cálculo actual es válido y utilizable |

---

## Instalación mediante HACS

1. Abre **HACS** en Home Assistant.
2. Ve a **Integraciones** → menú superior derecho (`⋮`) → **Repositorios personalizados**.
3. Añade la URL de este repositorio con categoría **Integración**.
4. Busca **Solar Battery Manager** e instálalo.
5. **Reinicia Home Assistant**.
6. Ve a **Ajustes → Dispositivos y servicios → Añadir integración** y busca **Solar Battery Manager**.

---

## Pruebas unitarias (desarrollo)

El motor de cálculo puro y la agregación horaria están desacoplados de Home Assistant y pueden probarse localmente con Python 3.13+:

```powershell
python -m unittest discover -s tests/unit -v
```

*(En Windows, requiere tener instalado `tzdata` para `ZoneInfo("Europe/Madrid")`.)*

---

## Documentación técnica

- [AGENTS.md](AGENTS.md) — Reglas de seguridad y arquitectura del proyecto.
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — Contexto de la instalación.
- [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) — Especificación funcional.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Hoja de ruta incremental.
