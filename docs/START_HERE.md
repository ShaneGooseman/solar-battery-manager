# Prompt inicial para Antigravity

Quiero desarrollar una integración personalizada de Home Assistant llamada `Solar Battery Manager`.

Lee primero:
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/TECHNICAL_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md`

No empieces a programar inmediatamente. Primero:
1. Resume lo que has entendido.
2. Identifica datos que faltan o supuestos que deben verificarse.
3. Propón una arquitectura compatible con la versión actual de Home Assistant.
4. Propón una estructura de carpetas y un plan de pruebas.
5. Señala cualquier riesgo de seguridad o limitación de la fórmula energética.

Restricciones obligatorias:
- La primera versión será solo lectura y simulación.
- No escribas en el inversor Deye ni cambies parámetros de batería.
- No inventes entidades ni servicios.
- No asumas que la capacidad nominal de 15 kWh es la capacidad útil.
- No asumas que el consumo de hoy será el consumo de mañana.
- Implementa primero cálculos puros y pruebas unitarias.
- Trabaja de forma incremental y espera mi aprobación antes de modificar archivos.

Contexto: quiero que la batería llegue al 100 % durante el día. Acepto utilizar la red durante la noche, en la ventana económica 00:00–08:00. El objetivo es calcular el SOC necesario a las 08:00 para que la producción solar prevista pueda completar la batería.
