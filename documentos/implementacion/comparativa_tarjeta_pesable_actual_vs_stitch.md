# Comparativa entre tarjeta pesable actual y modelo Stitch

## Objetivo

Este documento compara:

1. La implementacion actual de la tarjeta para productos pesables.
2. El modelo de referencia definido en Stitch.
3. Los cambios exactos necesarios para converger la implementacion real hacia ese modelo.

La comparativa se apoya en estas fuentes:

- `static/app.js`
- `documentos/implementacion/estructura_tarjetas_productos_pesables.md`
- `documentos/implementacion/estructura_modelo_stitch_tarjeta_pesable.md`
- `documentos/modelo_stitch/pesaje/DESIGN.md`
- `documentos/modelo_stitch/pesaje/code.html`

## Resumen ejecutivo

La implementacion actual ya adopta la base visual Electric Industrial, pero todavia no replica la estructura objetivo del modelo Stitch en tres puntos centrales:

1. El resumen superior sigue dividido en dos columnas `PAQ` y `DET`, mientras Stitch usa tres filas lineales: `SISTEMA`, `BARRA` y `DELTA`.
2. El bloque de captura fisica sigue basado en un input libre para `UNIDADES`, mientras Stitch propone un stepper para `Bot. Cerradas`.
3. Los pesos se capturan como una lista vertical de inputs, mientras Stitch propone una grilla compacta de tarjetas por botella.

## Comparativa por bloque

## 1. Contenedor general

### Implementacion actual

- Usa `.product-card` con `bg-surface-container`, `border-outline-variant`, `shadow-lg` y `chassis-panel`.
- Tiene una estetica industrial consistente, pero sin subcapas tan marcadas en el interior.

### Modelo Stitch

- Usa `chassis-panel` como contenedor principal.
- Agrega una capa de glow de foco con borde cyan al hover.
- La tarjeta se percibe como un panel tecnico con mayor profundidad visual.

### Brecha

- La base visual es compatible.
- Falta incorporar un tratamiento mas explicito del estado hover/focus del card y una separacion interna mas modular.

### Cambio exacto requerido

1. Agregar un overlay interno opcional de foco/glow al card.
2. Ajustar padding y ritmo interno para replicar el espaciamiento del modelo Stitch.

## 2. Cabecera del producto

### Implementacion actual

- Muestra categoria.
- Muestra nombre con glow cyan.
- Muestra `ID` y `Cód` en una linea inferior.

### Modelo Stitch

- Misma estructura base.
- La jerarquia visual esta mas refinada, con mejor aire entre bloques y una cabecera mas claramente separada por borde inferior.

### Brecha

- La estructura es practicamente equivalente.
- La diferencia es mayormente de ajuste fino visual, no funcional.

### Cambio exacto requerido

1. Mantener la estructura actual.
2. Ajustar paddings, espaciados y tamaños para acercarlos al modelo.
3. Confirmar un borde inferior mas limpio y consistente con Stitch.

## 3. Resumen comparativo superior

### Implementacion actual

Usa una grilla de dos columnas:

- Columna izquierda para `PAQ/SIST`, `PAQ/BARRA` y `dif-paq`.
- Columna derecha para `DET/SIST`, `DET/BARRA` y `dif-det`.

### Modelo Stitch

Usa tres filas apiladas:

1. `SISTEMA (Ideal)` con unidades y onzas.
2. `BARRA (Real)` con unidades y onzas.
3. `DELTA (R-I)` con diferencias en unidades y onzas.

Cada fila incluye:

- Un icono a la izquierda.
- Una etiqueta central.
- Dos valores a la derecha.

### Brecha

Esta es la diferencia estructural mas importante.

La implementacion actual separa por tipo de magnitud (`PAQ` y `DET`), mientras Stitch separa por nivel semantico (`SISTEMA`, `BARRA`, `DELTA`).

### Cambio exacto requerido

1. Reemplazar la grilla actual de 2 columnas por un stack vertical de 3 filas.
2. Consolidar unidades y onzas de sistema en una sola fila `SISTEMA (Ideal)`.
3. Consolidar unidades y onzas reales en una sola fila `BARRA (Real)`.
4. Consolidar las diferencias en una sola fila `DELTA (R-I)`.
5. Agregar iconos por fila:
   - `computer` para sistema
   - `local_bar` para barra
   - `stacked_line_chart` para delta
6. Mantener IDs funcionales internos para los valores calculados, aunque cambie el layout visual.

## 4. Lenguaje de interfaz

### Implementacion actual

- Usa `UNIDADES`.
- Usa `PESO`.

### Modelo Stitch

- Usa `Bot. Cerradas`.
- Usa `Bot 1 (g)`, `Bot 2 (g)`, etc.

### Brecha

- Hay una diferencia de naming y de especificidad.
- La implementacion actual es mas generica.
- Stitch es mas orientado a operacion de barra.

### Cambio exacto requerido

Definir una decision funcional antes de tocar codigo:

1. Opcion A: conservar `UNIDADES` y `PESO` por consistencia con negocio actual.
2. Opcion B: migrar a `Bot. Cerradas` y `Bot X (g)` para alinearse totalmente con Stitch.

Si se busca convergencia visual total, la opcion recomendada es la B.

## 5. Registro fisico

### Implementacion actual

- `UNIDADES` es un input numerico libre.
- `PESO` se presenta como contenedor de inputs verticales.
- Ambos viven en una fila de dos columnas responsive.

### Modelo Stitch

- El registro fisico esta contenido en un subpanel interno.
- Incluye una barra superior cyan luminosa.
- `Bot. Cerradas` usa un stepper.
- Los pesos se muestran en una grilla de dos columnas.

### Brecha

- La estructura general existe, pero no la forma del modulo.
- Falta un subpanel visual propio y falta cambiar el control de unidades.

### Cambio exacto requerido

1. Encapsular `UNIDADES/PESO` dentro de un subpanel `REGISTRO (Físico)`.
2. Agregar una barra superior luminosa de 4px.
3. Reemplazar el input libre de `UNIDADES` por un stepper con botones `+` y `-`.
4. Mantener sincronizacion del stepper con la logica actual de calculo.

## 6. Control de unidades cerradas

### Implementacion actual

- Input numerico `.input-cerradas`.
- El usuario escribe directamente el valor.

### Modelo Stitch

- Stepper con decremento, valor visible e incremento.

### Brecha

- La diferencia es funcional y visual.
- Stitch reduce la entrada manual y mejora el uso tactil.

### Cambio exacto requerido

1. Sustituir el `<input type="number">` visible por un control stepper.
2. Mantener un valor interno compatible con `.input-cerradas`.
3. Elegir una de estas estrategias de implementacion:
   - conservar `.input-cerradas` como input oculto y sincronizar botones
   - o mantener el input pero estilizarlo como stepper controlado
4. Actualizar eventos para que `recalcularTarjeta(card)` se dispare al incrementar o decrementar.

## 7. Bloque de pesos

### Implementacion actual

- Usa `#pesos-{id}`.
- Cada item usa `.item-peso-wrapper`.
- Los inputs se apilan en una sola columna.
- Puede incluir selector de perfil y boton eliminar para elementos agregados.

### Modelo Stitch

- Usa una grilla de 2 columnas.
- Cada botella parece una mini tarjeta con etiqueta propia e input a la derecha.
- La presentacion es mas compacta y escaneable.

### Brecha

- La logica actual ya soporta multiples botellas, pero el layout no coincide con Stitch.

### Cambio exacto requerido

1. Cambiar `.pesos-container` de lista vertical a grilla `grid-cols-2` en `sm` o incluso en movil si el ancho lo permite.
2. Rediseñar `crearInputPeso()` para que cada item se vea como tarjeta compacta.
3. Cambiar la etiqueta generica por un naming secuencial visible: `Bot 1 (g)`, `Bot 2 (g)`, etc.
4. Mantener compatibilidad con selector de perfil cuando existan multiples perfiles.
5. Definir ubicacion del boton eliminar para campos agregados sin romper la densidad visual.

## 8. Acciones inferiores

### Implementacion actual

- `+ Botella`.
- `+ Modelo`.
- Disposicion horizontal flexible.

### Modelo Stitch

- Misma idea estructural.
- Apariencia ghost mas precisa.
- Tipografia mas compacta.

### Brecha

- Diferencia baja.
- El patron ya existe y solo requiere refinamiento visual.

### Cambio exacto requerido

1. Reducir altura y ajustar padding para acercarse al modelo.
2. Ajustar tracking y tamaño de fuente segun Stitch.
3. Unificar hover glow para ambos botones.

## 9. Responsive

### Implementacion actual

- `UNIDADES` y `PESO` pasan de 1 columna a 2 columnas desde `sm`.
- Los pesos dentro del contenedor usan una sola columna.

### Modelo Stitch

- La tarjeta esta optimizada para movil.
- La grilla de pesos ya se ve en 2 columnas.

### Brecha

- El comportamiento responsive general es bueno.
- Falta adoptar la grilla compacta de pesos del modelo.

### Cambio exacto requerido

1. Evaluar si la grilla de pesos debe ser siempre de 2 columnas o solo desde cierto breakpoint.
2. Verificar legibilidad en 320px antes de fijar esa decision.

## 10. Compatibilidad con la logica actual

### Riesgo principal

La convergencia visual no debe romper:

- `.input-cerradas`
- `.input-peso`
- `.item-peso-wrapper`
- `.btn-add-peso`
- `.btn-add-modelo`
- `#val-paq-{id}`
- `#val-det-{id}`
- `#dif-paq-{id}`
- `#dif-det-{id}`
- `#pesos-{id_producto}`

### Regla de implementacion

El layout puede cambiar por completo, pero estos contratos funcionales deben preservarse o migrarse de forma controlada.

## Plan exacto de convergencia

### Fase 1: Reestructuracion visual del resumen superior

1. Reescribir el bloque HTML de metricas en `static/app.js`.
2. Sustituir la grilla `PAQ/DET` por tres filas `SISTEMA/BARRA/DELTA`.
3. Mapear los mismos datos actuales a la nueva estructura.

### Fase 2: Subpanel de registro fisico

1. Envolver el bloque de captura en un contenedor con borde completo.
2. Agregar barra superior cyan y titulo `REGISTRO (Físico)`.
3. Ajustar spacing interno.

### Fase 3: Stepper para botellas cerradas

1. Reemplazar el input directo por decremento/valor/incremento.
2. Mantener compatibilidad con el calculo actual.
3. Validar que nunca baje de 0.

### Fase 4: Rediseño del bloque de pesos

1. Cambiar `crearInputPeso()` para layout tipo mini-card.
2. Renderizar los pesos en grilla de 2 columnas.
3. Numerar visualmente las botellas.
4. Mantener logica de campo inicial no eliminable y campos agregados eliminables.

### Fase 5: Refinamiento final

1. Ajustar acciones `+ BOTELLA` y `+ MODELO`.
2. Revisar glow, bordes, pesos tipograficos y densidad.
3. Probar movil y desktop.

## Prioridad de cambios

Si hubiera que implementarlo en orden de impacto visual, el orden recomendado es:

1. Resumen superior `SISTEMA/BARRA/DELTA`.
2. Subpanel `REGISTRO (Físico)`.
3. Stepper de botellas cerradas.
4. Grilla de pesos por botella.
5. Ajustes menores de botones y spacing.

## Conclusión

La implementacion actual ya tiene una buena base funcional y de estilo, pero todavia esta a medio camino respecto del modelo Stitch.

La convergencia no requiere rehacer toda la logica; requiere principalmente:

1. Reestructurar el HTML que genera la tarjeta.
2. Cambiar el patron visual del registro fisico.
3. Transformar el input de unidades en stepper.
4. Rediseñar la presentacion del bloque de pesos.

La logica de calculo, identificadores y eventos puede mantenerse casi intacta si la migracion se hace preservando los hooks existentes.