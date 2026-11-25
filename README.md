# Solar Battery Manager

Integración personalizada para **Home Assistant Core (2026.11+)** que estima el excedente fotovoltaico diurno del día siguiente y calcula el **SOC objetivo mínimo** al finalizar la ventana económica nocturna (por defecto `00:00–08:00`) para que la producción solar pueda llevar la batería al 100 %.

> **Modo actual: Solo lectura y simulación (`v0.1.0`)**
> Esta versión **no escribe en el inversor** ni modifica parámetros de protección del BMS. Todos los cálculos y recomendaciones se exponen como sensores de solo lectura para validación.

---

## Características principales

- **Consumo diurno real (no 24 h)**: consulta las estadísticas horarias del `recorder` de Home Assistant únicamente dentro de la ventana solar configurada (excluyendo el consumo nocturno cubierto por la red).
- **Estimación explicable**: soporta `median` (por defecto) o `mean` sobre los últimos *N* días válidos, exponiendo en los atributos del sensor qué días se usaron y cuáles se descartaron.
- **Capacidad útil configurable**: no asume la capacidad nominal declarada de la batería ni toca límites internos del BMS.
- **Congelación pre-medianoche**: congela y persiste el objetivo diario (por defecto a las `23:55`) en el almacenamiento interno de Home Assistant para evitar variaciones por reinicios de sensores a medianoche o reinicios de HA.
- **Fallo seguro**: si faltan datos, un sensor está `unknown`/`unavailable` o no hay histórico suficiente, marca `binary_sensor.solar_battery_ready` en `off` y explica el motivo en `sensor.solar_battery_model_status`.

---

## Entidades creadas

| Entidad | Tipo | Descripción |
| :--- | :--- | :--- |
| `PV forecast tomorrow` | `sensor` (`kWh`) | Previsión fotovoltaica normalizada a kWh |
| `Daytime load forecast tomorrow` | `sensor` (`kWh`) | Consumo diurno estimado + traza de muestras usadas/descartadas |
| `Estimated solar surplus tomorrow` | `sensor` (`kWh`) | Excedente solar diurno estimado (`max(0, PV - consumo_diurno)`) |
| `Target SOC at 08:00` | `sensor` (`%`) | SOC objetivo calculado + atributos de trazabilidad y congelación |
| `Simulated grid energy required` | `sensor` (`kWh`) | Energía teórica necesaria desde red respecto al SOC actual |
| `Model status` | `sensor` | Estado del cálculo (`ok`, `insufficient_history`, etc.) |
| `Calculation ready` | `binary_sensor` | Indica si el cálculo actual es válido y utilizable |

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
- [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) — Especificación funcional y fórmulas.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Hoja de ruta incremental.
