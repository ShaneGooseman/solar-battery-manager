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
$$\text{excedente\_kWh} = \max\bigl(0,\; \text{previsión\_FV\_mañana\_kWh} - \text{consumo\_diurno\_kWh}\bigr)$$

### 4. Ganancia de SOC aportada por el sol (`ganancia_SOC_%`)
$$\text{ganancia\_SOC\_\%} = \frac{\text{excedente\_kWh} \times \eta_{\text{carga}}}{\text{capacidad\_útil\_kWh}} \times 100$$

Donde:
- $\text{capacidad\_útil\_kWh}$ es la capacidad real utilizable configurada por el usuario (no el nominal).
- $\eta_{\text{carga}}$ es la eficiencia de carga configurada (p. ej. `0,90` para `90 %`).

### 5. SOC objetivo al final de la ventana económica (`08:00`)
$$\text{SOC\_bruto\_\%} = 100 - \text{ganancia\_SOC\_\%} + \text{margen\_seguridad\_\%}$$

$$\text{SOC\_objetivo\_\%} = \text{redondear}\Bigl(\min\bigl(\text{SOC\_máx\_operativo},\; \max(\text{SOC\_mín\_operativo},\; \text{SOC\_bruto\_\%})\bigr)\Bigr)$$

### 6. Energía de red simulada necesaria (`energía_red_kWh`)
$$\Delta\text{SOC} = \max\bigl(0,\; \text{SOC\_objetivo\_\%} - \text{SOC\_actual\_\%}\bigr)$$

$$\text{energía\_red\_kWh} = \frac{(\Delta\text{SOC} / 100) \times \text{capacidad\_útil\_kWh}}{\eta_{\text{carga}}}$$

### 7. Hora de inicio de carga recomendada
A partir de la corriente máxima de carga desde red configurada (en A) y la tensión nominal de batería (por defecto `51,2 V`):

$$P_{\text{carga\_kW}} = \frac{I_{\text{máx\_red\_A}} \times V_{\text{nominal\_V}}}{1000}$$

$$\text{energía\_neta\_kWh} = \frac{\Delta\text{SOC}}{100} \times \text{capacidad\_útil\_kWh}$$

$$\text{duración\_min} = \left\lceil \frac{\text{energía\_neta\_kWh}}{P_{\text{carga\_kW}}} \times 60 \right\rceil + \text{margen\_tiempo\_min}$$

$$\text{hora\_inicio} = \max\bigl(\text{inicio\_tarifa},\; \text{fin\_tarifa} - \text{duración\_min}\bigr)$$

Si $\text{duración\_min}$ supera la duración de la ventana económica, se fija el inicio al principio de la ventana (`00:00`) y se indica en los atributos (`can_reach_target_in_window: false`).

### 8. Congelación pre-medianoche
Al llegar la hora de congelación configurada (por defecto `23:55`), el **SOC objetivo** queda congelado y guardado en el almacenamiento interno de Home Assistant para toda la ventana nocturna (`00:00–08:00`), evitando que los reinicios diarios de sensores a las `00:00` o un reinicio de Home Assistant alteren el objetivo.

---

### Ejemplo numérico paso a paso

Supongamos:
- Previsión FV mañana: `11,91 kWh`
- Consumo diurno estimado (mediana): `5,10 kWh`
- Capacidad útil configurada: `12,0 kWh` | Eficiencia: `90 %` | Margen seguridad: `5 %`
- SOC actual: `60 %` | Corriente máx. red: `25 A` @ `51,2 V` | Margen tiempo: `15 min`

1. **Excedente**: $\max(0,\; 11,91 - 5,10) = \mathbf{6,81\text{ kWh}}$
2. **Ganancia solar**: $(6,81 \times 0,90 / 12,0) \times 100 = \mathbf{51,08\text{ \%}}$
3. **SOC objetivo**: $100 - 51,08 + 5 = 53,92 \rightarrow \mathbf{54\text{ \%}}$ *(si el SOC actual es 60 %, no requiere carga de red)*
4. Si el SOC actual fuese **40 %** ($\Delta\text{SOC} = 14\text{ \%}$):
   - Energía neta a añadir: $0,14 \times 12,0 = 1,68\text{ kWh}$
   - Energía de red estimada: $1,68 / 0,90 = \mathbf{1,87\text{ kWh}}$
   - Potencia de carga: $25 \times 51,2 / 1000 = \mathbf{1,28\text{ kW}}$
   - Duración: $\lceil (1,68 / 1,28) \times 60 \rceil + 15 = 79 + 15 = \mathbf{94\text{ min}}$
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
