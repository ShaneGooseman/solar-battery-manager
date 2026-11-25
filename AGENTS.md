# Reglas del proyecto — Solar Battery Manager

## Forma de trabajar
- Trabaja incrementalmente: una fase pequeña, verificable y probada cada vez.
- Antes de modificar archivos, inspecciona el repositorio y presenta un plan breve.
- No inventes entidades, servicios, atributos ni capacidades de integraciones externas. Verifica los identificadores en la configuración o pide al usuario los datos que falten.
- Explica qué archivos vas a crear o modificar y por qué.
- Añade pruebas para los cálculos y casos límite.
- Mantén documentación actualizada.

## Seguridad y control del inversor
- El modo inicial y predeterminado debe ser SIMULACIÓN; nunca escribir en el inversor.
- No activar control real del Deye sin autorización explícita del usuario.
- No modificar protecciones, límites de corriente/tensión, parámetros BMS, límites de descarga, límites de temperatura ni parámetros de seguridad.
- Cualquier control real debe tener límites configurables, validación de datos, condiciones de parada y registro de acciones.
- Si falta una entidad o un dato está `unknown`, `unavailable`, obsoleto o fuera de rango, fallar de forma segura y no ordenar carga.
- No asumir que una escritura a una entidad del inversor ha tenido éxito: verificar el estado resultante.

## Arquitectura
- Implementación como integración nativa de Home Assistant bajo `custom_components/solar_battery_manager/`.
- Usar APIs públicas y patrones soportados por la versión objetivo de Home Assistant.
- Configuración mediante Config Flow y opciones; evitar YAML manual para el usuario.
- Separar cálculo energético, estimación de consumo, coordinación de datos y control del inversor.
- No acoplar el núcleo a Deye/ Solarman: definir una capa/adaptador de control intercambiable.
- No añadir dependencias externas sin justificar y documentar su mantenimiento.

## Calidad
- Tipado, validación de entradas, logs útiles y diagnósticos sin exponer secretos.
- Pruebas unitarias de fórmulas, límites, medianoche, horario de tarifa y datos ausentes.
- No afirmar compatibilidad con una versión de Home Assistant hasta probarla.
