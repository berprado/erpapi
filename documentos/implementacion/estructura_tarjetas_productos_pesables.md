# Estructura de tarjetas para productos pesables

## Objetivo

Este documento describe la estructura visual y funcional de las tarjetas que se renderizan para productos pesables en la pantalla de inventario BackStage.

La referencia principal de implementacion actual esta en `static/app.js`, dentro del bloque que construye el HTML dinamico de cada `.product-card`.

## Datos base de la tarjeta

Cada tarjeta de producto pesable almacena informacion clave en atributos `data-*` para soportar calculos en tiempo real y envio al backend.

- `data-id`: identificador del producto.
- `data-pesable`: indica si el producto requiere pesaje.
- `data-nombre`: nombre visible del producto.
- `data-perfiles`: perfiles de botella serializados en JSON.
- `data-tolerancia`: tolerancia en onzas usada para validacion.
- `data-paqsist`: stock ideal en unidades.
- `data-detsist`: stock ideal en onzas.

## Estructura general de la tarjeta

La tarjeta se compone de cuatro bloques principales:

1. Cabecera informativa.
2. Resumen comparativo sistema vs barra.
3. Zona de captura de inventario.
4. Acciones para ampliar el pesaje.

## 1. Cabecera informativa

La cabecera muestra el contexto del producto.

- Categoria, si existe.
- Nombre del producto.
- ID interno.
- Codigo del producto.

## 2. Resumen comparativo sistema vs barra

Para productos pesables, la tarjeta muestra una grilla de 2 columnas:

### Columna izquierda: PAQ

- `PAQ/SIST`: unidades esperadas por sistema.
- `PAQ/BARRA`: unidades capturadas en la barra.
- `dif-paq-{id}`: diferencia entre sistema y barra.

### Columna derecha: DET

- `DET/SIST`: onzas esperadas por sistema.
- `DET/BARRA`: onzas calculadas desde los pesos capturados.
- `dif-det-{id}`: diferencia entre sistema y barra.

## 3. Zona de captura de inventario

La captura principal esta organizada como una fila responsive:

- En movil: una sola columna.
- Desde `sm`: dos columnas lado a lado.

### Columna A: UNIDADES

Contiene un input numerico:

- Etiqueta: `UNIDADES`.
- Clase funcional: `.input-cerradas`.
- Uso: registrar botellas cerradas.

### Columna B: PESO

Contiene el bloque de captura de botellas abiertas:

- Etiqueta: `PESO`.
- Contenedor: `#pesos-{id_producto}`.
- Contenido inicial: un campo de peso por defecto.

### Regla funcional del campo inicial de peso

El primer campo de peso es obligatorio como base visual y funcional del producto pesable.

- Se renderiza con `crearInputPeso(perfilesJson, false)`.
- No muestra boton de eliminar.
- No debe poder quitarse manualmente.

## 4. Acciones de ampliacion del pesaje

Debajo del contenedor de pesos se muestran dos botones:

### Boton AGREGAR BOTELLA

- Clase funcional: `.btn-add-peso`.
- Agrega un nuevo input de peso dentro de `#pesos-{id_producto}`.
- Los campos agregados se crean con `crearInputPeso(perfiles, true)`.
- Estos campos si incluyen boton de eliminar.

### Boton NUEVO MODELO

- Clase funcional: `.btn-add-modelo`.
- Permite crear un nuevo perfil o modelo de botella.

## Estructura del input de peso

Cada item dentro del contenedor de pesos usa la clase `.item-peso-wrapper` y puede incluir:

- Un selector de perfil `.select-perfil` si el producto tiene mas de un perfil.
- Un input numerico `.input-peso`.
- Un boton de cierre solo si el campo es removible.

## Reglas funcionales actuales

Las reglas actuales de comportamiento para productos pesables son:

1. Siempre existe un campo inicial de peso.
2. El campo inicial no se puede eliminar.
3. Los campos agregados con `AGREGAR BOTELLA` si se pueden eliminar.
4. `UNIDADES` y `PESO` comparten la misma fila visual en pantallas medianas o mayores.
5. En pantallas chicas, `UNIDADES` y `PESO` se apilan para mantener legibilidad.

## Selectores y nodos clave

Los selectores funcionales mas importantes son:

- `.product-card`
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

## Flujo resumido

1. Se renderiza la tarjeta con datos base del producto.
2. Se muestran comparativos PAQ y DET.
3. El usuario registra `UNIDADES`.
4. El usuario registra `PESO` con un campo inicial fijo.
5. Si necesita mas botellas abiertas, usa `AGREGAR BOTELLA`.
6. Los calculos actualizan `PAQ/BARRA`, `DET/BARRA` y las diferencias en tiempo real.

## Ubicacion de implementacion

La implementacion activa de esta estructura se encuentra principalmente en:

- `static/app.js`

Cambios futuros sobre layout, inputs o comportamiento de pesaje deben actualizar este documento para mantener alineada la documentacion funcional con la interfaz real.