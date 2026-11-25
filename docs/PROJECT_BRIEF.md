# Project Brief — Solar Battery Manager

> **Nota histórica**: este documento recoge el punto de partida inicial de la instalación antes del desarrollo de la integración. Para la arquitectura, entidades y estado actual (`v0.2.4`), consulta [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) y [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Objetivo

Crear una integración personalizada de Home Assistant que estime cuánta energía solar sobrante habrá mañana y calcule el SOC mínimo al que debe llegar la batería a las 08:00, utilizando la red durante la ventana económica nocturna (00:00–08:00) cuando sea necesario.

La prioridad del usuario es que la batería pueda llegar al 100 % durante el día. No es necesario reservar batería para cubrir la noche siguiente: el usuario acepta consumir de la red durante la noche.

## Instalación conocida

- Ubicación: Guardamar del Segura, Alicante, España.
- Home Assistant OS 18.4 en una VM de Proxmox.
- Inversor híbrido monofásico: Deye SUN-5K-SG03LP1-EU, 5 kW, batería de 48 V.
- Batería: Felicity Solar Lux-Y FLA48300, 48 V, 300 Ah; capacidad nominal declarada de 15 kWh.
- Fotovoltaica: dos orientaciones, sur y oeste; 6 paneles JA Solar de 535 W por string; inclinación aproximada de 30 grados.
- El string oeste sufre sombras importantes.
- La producción real conjunta de invierno se ha situado aproximadamente en torno a 12 kWh/día según lo comentado por el usuario; tratarlo como referencia aproximada, no como dato garantizado.
- Ventana de tarifa económica para cargar desde red: 00:00–08:00.

## Entidades confirmadas en Home Assistant

### Integración Machine-Learning-Based PV Forecast
- Previsión de mañana: `sensor.pv_forecast_total_tomorrow`
- Estado del modelo observado: `Ready`
- Producción de hoy observada en la integración: 8,90 kWh en la captura compartida.
- Previsión de mañana observada: 11,93 kWh en la captura compartida.
- La integración también expone sensores de curva, producción hoy, pico de potencia, hit rate y errores; algunos diagnósticos aparecían inicialmente como desconocidos.

### Deye / Solarman
- Producción diaria: `sensor.inversordeye_today_production`
- Potencia PV1: `sensor.inversordeye_pv1_power`
- Potencia PV2: `sensor.inversordeye_pv2_power`
- Consumo diario vivienda: `sensor.inversordeye_today_load_consumption`
- Consumo instantáneo: `sensor.inversordeye_load_power`
- SOC batería: `sensor.inversordeye_battery`

Debe verificarse en la instalación la unidad, clase de estado, estadísticas y disponibilidad de cada sensor antes de basar cálculos de producción/consumo en ellos.

## Helpers creados durante la conversación

- Sensor de excedente: `sensor.excedente_solar_previsto_manana`
  - Fórmula provisional: máximo entre cero y previsión de mañana menos consumo diario de hoy.
  - Valor observado: 4,33 kWh.
- Sensor SOC objetivo: `sensor.soc_objetivo_a_las_08_00`
  - Valor observado: 79 %.
  - Fórmula provisional: SOC objetivo = 100 − (excedente × 0,90 / 15 × 100) + 5, limitado a 0–100.
- Número para persistir objetivo nocturno: `input_number.soc_objetivo_nocturno`
  - Paso 1, mínimo 0, máximo 100.
  - Tras ejecutar manualmente una automatización de prueba, mostraba 80,0; diferencia debida al redondeo/paso entero.

## Estado actual

El usuario ha creado los ayudantes y una automatización visual para guardar el objetivo nocturno. La acción se configuró para copiar el estado de `sensor.soc_objetivo_a_las_08_00` a `input_number.soc_objetivo_nocturno`. Se vio el helper en 80,0 tras la prueba.

La automatización se había configurado inicialmente para las 23:59 (aunque se había hablado de 23:55). Confirmar la hora final y revisar el YAML real antes de asumir que está correctamente configurada.

No se ha implementado ninguna integración personalizada todavía. No se ha autorizado controlar el inversor automáticamente.

## Preferencias del usuario

- Quiere instrucciones claras, directas y paso a paso.
- Prefiere configurar Home Assistant mediante interfaz gráfica siempre que sea razonable.
- Quiere una solución sencilla y robusta; evitar complejidad innecesaria.
- Desarrollar primero simulación y validación; después valorar control real.
