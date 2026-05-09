# Estructura del modelo Stitch de tarjeta para productos pesables

## Objetivo

Este documento describe la estructura visual y funcional del modelo de tarjeta para productos pesables definido en la referencia Stitch de pesaje.

La descripcion se basa en tres fuentes de referencia:

1. La captura visual del modelo.
2. El archivo `documentos/modelo_stitch/pesaje/DESIGN.md`.
3. El archivo `documentos/modelo_stitch/pesaje/code.html`.

Este documento no describe la implementacion actual en produccion, sino el modelo visual de referencia que sirve como objetivo de diseño.

## Identidad visual del modelo

La tarjeta responde al sistema visual Electric Industrial.

Sus rasgos principales son:

- Fondo oscuro de alta densidad.
- Tipografia `Space Grotesk` para todo el contenido.
- Bordes finos con `outline-variant`.
- Acentos Electric Cyan para estados activos y datos de prioridad.
- Uso de `secondary` para el bloque de delta.
- Sensacion de consola tecnica o panel de control industrial.

## Estructura general de la tarjeta

La tarjeta esta organizada en cuatro zonas principales:

1. Cabecera del producto.
2. Bloque de metricas comparativas.
3. Bloque de registro fisico.
4. Bloque de acciones.

El contenedor general usa un panel estructural tipo `chassis-panel`, con borde sutil y posibilidad de glow al interactuar.

## 1. Cabecera del producto

La cabecera aparece en la parte superior de la tarjeta y contiene:

- Categoria en estilo `label-mono`, uppercase y tracking amplio.
- Nombre del producto en estilo `headline-md` con glow cyan.
- Metadata inferior con ID y codigo separados por un divisor vertical.

### Jerarquia visual

- Categoria: informativa, secundaria.
- Nombre: dato dominante de la tarjeta.
- ID y codigo: metadata compacta en `data-tabular`.

## 2. Bloque de metricas comparativas

Debajo de la cabecera se presenta una pila vertical de tres filas comparativas.

### Fila 1: SISTEMA (Ideal)

Representa el valor esperado por sistema.

Elementos:

- Icono a la izquierda: `computer`.
- Etiqueta: `SISTEMA (Ideal)`.
- Valores a la derecha: botellas y onzas.
- Fondo `surface-container-low`.
- Borde `outline-variant`.

### Fila 2: BARRA (Real)

Representa el valor real capturado en barra.

Elementos:

- Icono a la izquierda: `local_bar`.
- Etiqueta: `BARRA (Real)`.
- Valores a la derecha: botellas y onzas.
- Color dominante: `primary-fixed-dim`.
- Borde cyan de enfasis.

### Fila 3: DELTA (R-I)

Representa la diferencia entre real e ideal.

Elementos:

- Icono a la izquierda: `stacked_line_chart`.
- Etiqueta: `DELTA (R-I)`.
- Valores a la derecha: diferencia en botellas y en onzas.
- Color dominante: `secondary`.
- Glow secundario para destacar la diferencia.

### Patron estructural comun de las tres filas

Las tres filas comparten un mismo patron:

- Zona izquierda fija para icono.
- Zona derecha flexible con separador vertical.
- Etiqueta alineada a la izquierda.
- Datos alineados a la derecha.
- Un solo renglon para mantener densidad visual.

## 3. Bloque de REGISTRO (Físico)

Este modulo se presenta como una sub-seccion contenida dentro de la tarjeta.

Rasgos visuales:

- Contenedor con borde completo.
- Barra superior cyan de 4px con glow.
- Titulo `REGISTRO (Físico)` en uppercase.
- Layout interno con ritmo vertical compacto.

Este bloque contiene dos subzonas:

1. Control de botellas cerradas.
2. Grilla de pesos por botella.

## 3.1 Control de botellas cerradas

El modelo Stitch utiliza un stepper, no un input libre.

Estructura:

- Etiqueta: `Bot. Cerradas`.
- Boton de decremento con icono `remove`.
- Valor numerico central destacado.
- Boton de incremento con icono `add`.

### Intencion funcional

Este control sugiere un flujo de conteo rapido en campo, orientado a minimizar escritura manual y errores de dedo.

## 3.2 Grilla de pesos por botella

Debajo del stepper aparece una grilla de 2 columnas con los pesos de botellas abiertas.

Cada item de la grilla incluye:

- Etiqueta de botella, por ejemplo `Bot 1 (g)`.
- Input alineado a la derecha para el peso.
- Contenedor individual con borde y fondo profundo.

### Patron visual de cada item

- Layout horizontal entre etiqueta e input.
- Input compacto de ancho fijo.
- Texto de datos en color cyan o primario.
- Caja interna del input con sombra inset para efecto tecnico.

## 4. Bloque de acciones

En la parte inferior del modulo de registro aparece una fila de dos botones de accion:

1. `+ BOTELLA`
2. `+ MODELO`

Ambos botones comparten un mismo patron:

- Ancho flexible equivalente.
- Borde `outline-variant`.
- Estilo ghost.
- Texto `label-mono` uppercase.
- Hover con cambio a cyan y glow.

## Comportamiento responsive observado

Con base en la captura y el HTML de referencia:

- La tarjeta esta pensada para ancho movil primero.
- La grilla de pesos usa 2 columnas dentro del ancho disponible.
- La barra inferior de navegacion esta visible solo en movil (`md:hidden`).
- El contenido principal se centra en una columna con `max-w-2xl`.

## Tokens y estilos relevantes del modelo

Los tokens mas representativos usados por este modelo son:

- `surface`, `surface-container-low`, `surface-container`, `surface-container-lowest`.
- `primary`, `primary-fixed`, `primary-fixed-dim`.
- `secondary`.
- `outline-variant`.
- `label-mono`, `headline-md`, `data-tabular`.

Clases visuales destacadas:

- `chassis-panel`
- `glow-border`
- `glow-border-secondary`
- `neon-text-primary`
- `neon-text-secondary`

## Diferencias clave contra la implementacion actual del proyecto

Este modelo Stitch presenta varias diferencias frente a la tarjeta actualmente implementada en `static/app.js`:

1. El registro fisico esta encapsulado en un subpanel con barra superior luminosa.
2. `Bot. Cerradas` usa stepper con botones `+` y `-` en lugar de un input directo.
3. Los pesos se muestran como una grilla de tarjetas compactas por botella.
4. El resumen superior esta organizado como tres filas lineales: sistema, barra y delta.
5. El lenguaje del modelo usa `Bot. Cerradas` y `Bot X (g)` como etiquetas de referencia.

## Estructura resumida del modelo

La jerarquia completa del card puede leerse asi:

1. Contenedor principal `chassis-panel`.
2. Cabecera: categoria, nombre, ID, codigo.
3. Tres filas metricas: sistema, barra, delta.
4. Subpanel `REGISTRO (Físico)`.
5. Stepper de botellas cerradas.
6. Grilla de pesos por botella en 2 columnas.
7. Fila inferior de acciones `+ BOTELLA` y `+ MODELO`.

## Uso recomendado de este documento

Este documento sirve para:

- Guiar una futura migracion visual hacia el modelo Stitch.
- Comparar la implementacion actual con la referencia de diseño.
- Mantener documentado el objetivo de UI para productos pesables.

Si se implementa este modelo en la aplicacion real, conviene actualizar tambien la documentacion existente para distinguir claramente entre:

- estructura actual implementada
- estructura objetivo basada en Stitch