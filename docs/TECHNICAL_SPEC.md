# Especificación técnica — Solar Battery Manager

## 1. Comportamiento funcional

Cada día, antes de la ventana de carga nocturna, la integración debe:

1. Obtener previsión de producción fotovoltaica para el día siguiente desde una entidad seleccionada por el usuario.
2. Estimar el consumo de la vivienda para el día siguiente a partir de histórico de consumo real. En primera versión se puede permitir una estrategia sencilla seleccionable (por ejemplo, promedio de los últimos N días comparables), pero no asumir que el consumo de hoy equivale siempre al de mañana.
3. Estimar excedente energético disponible para cargar batería.
4. Convertir el excedente en incremento de SOC, teniendo en cuenta capacidad útil configurable y eficiencia configurable.
5. Calcular SOC objetivo a las 08:00 para que la energía solar disponible pueda completar la batería hasta el 100 %, con margen de seguridad configurable.
6. Guardar/congelar el objetivo calculado antes de las 00:00 para que no cambie durante la madrugada por reinicios diarios de sensores.
7. Mostrar recomendación y diagnóstico en Home Assistant.
8. Inicialmente, no controlar el inversor.

## 2. Fórmulas iniciales

Definiciones:
- `pv_forecast_kwh`: energía FV prevista para mañana.
- `house_load_forecast_kwh`: consumo de la vivienda previsto para mañana.
- `surplus_kwh`: excedente solar estimado.
- `usable_battery_kwh`: capacidad útil de batería, configurable.
- `charge_efficiency`: eficiencia global de carga, configurable.
- `safety_margin_soc`: margen de seguridad en puntos porcentuales.

Cálculo inicial:
`surplus_kwh = max(0, pv_forecast_kwh - house_load_forecast_kwh)`

Incremento de SOC aproximado:
`solar_soc_gain = surplus_kwh * charge_efficiency / usable_battery_kwh * 100`

SOC objetivo:
`target_soc = clamp(100 - solar_soc_gain + safety_margin_soc, min_soc, 100)`

NOTA: Esta fórmula es un modelo simplificado. Debe revisarse si el excedente solar no está realmente disponible para cargar la batería durante las horas útiles, si hay límites de potencia, consumo horario, restricciones de exportación, pérdidas adicionales o capacidad útil distinta de la nominal. No tratar el resultado como una garantía de alcanzar el 100 %.

La capacidad de 15 kWh es nominal declarada; permitir configurar capacidad útil real. La eficiencia del 90 % y el margen de 5 puntos se utilizaron solo como parámetros iniciales provisionales.

## 3. Entidades sugeridas

Los nombres finales deben respetar las convenciones de Home Assistant y evitar colisiones. Propuesta:

- `sensor.solar_battery_pv_forecast_tomorrow`
- `sensor.solar_battery_load_forecast_tomorrow`
- `sensor.solar_battery_surplus_tomorrow`
- `sensor.solar_battery_target_soc`
- `sensor.solar_battery_grid_energy_required`
- `sensor.solar_battery_recommended_charge`
- `sensor.solar_battery_forecast_error`
- `binary_sensor.solar_battery_ready`
- `sensor.solar_battery_model_status`

Exponer atributos de diagnóstico: timestamp del cálculo, entidades fuente, valores de entrada, calidad/validez de datos, parámetros utilizados y motivo de fallback.

## 4. Configuración

Config Flow / Options Flow para:
- entidad de previsión FV (en la instalación actual `sensor.pv_forecast_total_tomorrow`);
- entidad de consumo histórico o sensor de energía diaria;
- entidad SOC de batería;
- capacidad nominal y capacidad útil configurable;
- eficiencia de carga;
- margen de seguridad;
- SOC mínimo/máximo operativo (sin modificar límites de protección del BMS/inversor);
- horario de tarifa económica (actualmente 00:00–08:00);
- zona horaria local;
- modo simulación (activado por defecto);
- futura selección de integración/adaptador de control.

Validar unidades, `device_class`, `state_class`, disponibilidad y estadísticas cuando aplique. No depender solo del nombre de entidad.

## 5. Estimación de consumo

No asumir que `sensor.inversordeye_today_load_consumption` representa el consumo de mañana ni que el estado actual es válido a cualquier hora.

Investigar qué método fiable ofrece Home Assistant para recuperar estadísticas históricas del sensor. Evaluar:
- estadísticas de largo plazo;
- media/mediana de últimos 7/14/30 días;
- días laborables frente a fines de semana;
- patrón horario de consumo para estimar consumo durante horas solares.

Empezar con una solución sencilla y explicable. Exponer el método y calidad de estimación.

## 6. Control de carga: fase futura

No implementar ni activar hasta autorización explícita.

Antes de escribir al Deye:
- identificar el mecanismo real y soportado para controlar carga desde red (entidad/servicio Modbus, integración o API);
- verificar cómo se establece el límite de carga y el SOC objetivo;
- verificar lectura posterior y comportamiento de fallo;
- asegurar que la estrategia no cambia protecciones ni parámetros BMS;
- incluir límites de corriente configurables conservadores, parada por SOC objetivo, hora límite 08:00 y cancelación si los datos no son válidos;
- no usar entidades inventadas ni asumir que una entidad `number` equivale a una orden de carga;
- añadir un interruptor de habilitación explícita para control real, desactivado por defecto.

## 7. Pruebas

Unit tests para:
- excedente negativo y cero;
- previsión o consumo unknown/unavailable;
- valores fuera de rango;
- capacidad útil cero/inválida;
- eficiencia y margen extremos;
- redondeos y clamp;
- cambios de día y reinicios;
- congelación del objetivo nocturno;
- cambio horario y zona horaria;
- datos históricos insuficientes.

Probar en Home Assistant en modo simulación durante varios días y comparar previsión con producción real y consumo previsto con consumo real.
