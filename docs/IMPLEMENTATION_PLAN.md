# Plan de implementación

## Fase 0 — Inspección y decisiones
- Revisar versión exacta de Home Assistant Core.
- Confirmar integración y entidades disponibles.
- Confirmar atributos/unidades/estadísticas de sensores de producción y consumo.
- Revisar estado real de la automatización que guarda `input_number.soc_objetivo_nocturno`.
- Definir cómo se consultarán estadísticas históricas desde la integración.

Entregable: decisiones técnicas y mapa de entidades verificado.

## Fase 1 — Integración en modo solo lectura
- Crear estructura `custom_components/solar_battery_manager/`.
- Config Flow para seleccionar sensores y parámetros.
- Coordinator para leer sensores.
- Módulo puro de cálculos energéticos.
- Sensores de previsión, consumo, excedente y SOC objetivo.
- Diagnósticos y logs.
- Sin escritura a ninguna entidad del inversor.

Entregable: integración instalable y entidades de cálculo.

## Fase 2 — Persistencia y simulación
- Persistir el SOC objetivo diario calculado.
- Congelar objetivo antes de medianoche.
- Simular ventana de red 00:00–08:00.
- Calcular energía teórica necesaria para llegar al SOC objetivo.
- Registrar previsión frente a resultado real.

Entregable: historial de simulación y dashboard recomendado.

## Fase 3 — Validación
- Ejecutar varios días, incluyendo días despejados y nublados.
- Comparar producción prevista y real.
- Comparar consumo previsto y real.
- Ajustar capacidad útil, eficiencia y margen con datos reales.
- No activar control automático todavía.

Criterio de salida: precisión y comportamiento suficientemente estables y entendidos por el usuario.

## Fase 4 — Adaptador de control Deye (solo con autorización)
- Investigar entidad/servicio de control real disponible en la instalación.
- Implementar adaptador separado del motor de cálculo.
- Añadir enable switch, límites, timeout, verificación de escritura y fallback seguro.
- Mantener protecciones del inversor/BMS intactas.
- Pruebas supervisadas y plan de reversión.

Entregable: control opt-in, documentado y desactivado por defecto.
