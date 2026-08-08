---
description: "Refactorizar el modal de pour cost para que muestre las cantidades con las unidades correctas"
name: "Pour Cost Modal Refactor"
applyTo: "**"
---
Necesito refactorizar la representación y edición de cantidades de los ingredientes en la ventana modal de la pestaña **COCTELES** del módulo **POUR COST**.

Esta tarea debe limitarse a mostrar las cantidades en la unidad práctica de la receta y permitir modificarlas en intervalos de `0,5`. 

## Fuentes de contexto

Revisa antes de modificar:

1. La implementación actual del modal.
2. La API y los esquemas utilizados por POUR COST.
3. `documentos/pour_cost/pourcost.md`.
4. `querys/create_views_pourcost.sql`.
5. La definición vigente de `vw_combo_detalle_reload`.
6. La definición vigente de `vw_pourcost_receta`.
7. Las capturas y recetas de:

   * V Long Island Iced Tea.
   * V Chuflay.
   * Referencias visuales:
     - [documentos/pour_cost/long_island.png](../../documentos/pour_cost/long_island.png)
     - [documentos/pour_cost/chuflay.png](../../documentos/pour_cost/chuflay.png)

El código y las vistas desplegadas deben considerarse la fuente de verdad. Si difieren de la documentación, informa la discrepancia y actualiza la documentación al finalizar.

## Diagnóstico breve de alineación con la implementación actual

- El flujo actual del backend ya expone `cantidad_receta` y `cantidad_unidad_base` desde `vw_pourcost_receta`, pero el modal actual sigue editando la fracción de presentación (`cantidad_unidad_base`) en vez de la cantidad visible de receta.
- El contrato actual del frontend/backend debe conservar `ind_tipo_producto` y `tipo_parte_combo` para no perder el contexto de ingredientes principales y opcionales; este punto debe quedar explícito en la respuesta del endpoint y en el estado local de simulación.
- La UI actual muestra un texto genérico de presentación como `Presentación: ML`; la refactorización debe reemplazarlo por una presentación estructurada de envase y rendimiento basada en las columnas de medida de la vista.

# Problema actual

El campo `CANT.` muestra la proporción del envase consumida:

```text
cantidad_unidad_base =
cantidad_combo / cantidad_detalle
```

Ejemplo para 37 LENGUAS:

```text
cantidad_combo:     1 oz
cantidad_detalle:   34 oz
cantidad mostrada:  1 / 34 = 0,029412
```

La conversión es correcta para calcular el costo, pero no resulta comprensible para el usuario.

La vista `vw_combo_detalle_reload` ya contiene la cantidad y la unidad utilizadas en la receta:

```text
cantidad_combo
tipo_cantidad_combo
cantidad_detalle
nombre_unidad_medida_detalle
medida
nombre_unidad_medida
```

Por tanto, el frontend no debe reconstruir la cantidad desde la fracción ni desde el nombre del producto.

# Comportamiento esperado

Para ingredientes de tipo `Detalle`, muestra:

```text
cantidad_combo + nombre_unidad_medida_detalle
```

Ejemplos:

```text
37 LENGUAS:      1 OZ
CASA REAL NEGRA: 1,5 OZ
COCA-COLA:       4 OZ
SPRITE:          4 OZ
```

La cantidad debe editarse mediante:

```text
[−] [cantidad] [+] unidad
```

Ejemplo:

```text
[−] [1,5] [+] OZ
```

## Comportamiento del selector

* El botón `−` resta `0,5`.
* El botón `+` suma `0,5`.
* La cantidad mínima es cero.
* El campo central permite ingreso manual.
* Debe admitir coma o punto decimal si la interfaz ya contempla configuración regional en español.
* Debe normalizar valores como `1`, `1,0` y `1.0`.
* No debe producir errores binarios como `1,499999999`.
* Debe mostrar la unidad al lado del campo.
* Los botones deben tener un área táctil apropiada.
* El cambio debe recalcular inmediatamente el costo de la línea y los totales actuales del modal.

No asumas que todos los ingredientes están expresados en onzas. El incremento de `0,5` aplica a `Oz.`. Para otras unidades, conserva la interpretación existente o define el incremento según una regla comprobada.

## Aclaraciones de consistencia para la implementación

* La fuente de verdad para la cantidad visible debe ser `cantidad_receta` y la unidad proveniente de la vista; no se debe reconstruir el valor a partir del nombre del producto.
* La edición solo debe afectar `cantidad_receta`. `cantidad_unidad_base` debe calcularse internamente a partir de esa cantidad y no exponerse como campo editable.
* La normalización del ingreso debe aceptar valores como `1`, `1.0`, `1,0` y `1,5`, y convertirlos a un valor decimal estable antes de calcular.
* Los valores vacíos, negativos o no numéricos deben rechazarse y no deben propagarse al cálculo del costo.
* Deben conservarse `ind_tipo_producto` y `tipo_parte_combo` en el contrato de datos para no perder el contexto de ingredientes principales y opcionales.

# Separación entre cantidad visible y cantidad de costeo

Conserva dos conceptos separados:

```text
cantidad_receta
cantidad_unidad_base
```

Para una línea de tipo `Detalle`:

```text
cantidad_receta = cantidad_combo

cantidad_unidad_base =
cantidad_receta / cantidad_detalle

cogs_ingrediente =
cantidad_unidad_base × wac_actual
```

Para una línea de tipo `Unidad`:

```text
cantidad_receta = cantidad_combo

cantidad_unidad_base =
cantidad_receta

cogs_ingrediente =
cantidad_receta × wac_actual
```

El usuario debe editar `cantidad_receta`.

`cantidad_unidad_base` debe calcularse internamente y no debe presentarse como cantidad de preparación.

No redondees `cantidad_unidad_base` antes de calcular el costo.

# Información de envase y rendimiento

Reemplaza textos incompletos como:

```text
PRESENTACIÓN: ML
```

Por información estructurada:

```text
ENVASE: 1000 ML · RENDIMIENTO: 34 OZ
```

Mapeo:

```text
ENVASE:
medida + nombre_unidad_medida

RENDIMIENTO:
cantidad_detalle + nombre_unidad_medida_detalle
```

Ejemplos:

```text
JARANA SILVER:
ENVASE: 750 ML · RENDIMIENTO: 25,50 OZ

COCA-COLA:
ENVASE: 3000 ML · RENDIMIENTO: 101,50 OZ

GINGER ALE:
ENVASE: 2000 ML · RENDIMIENTO: 67,50 OZ
```

No extraigas medidas desde nombres como `1LT`, `750ML` o `3LT`.

# Estado de la simulación

Al abrir el modal, conserva una copia inmutable de:

* Cantidades originales de receta.
* WAC originales.
* Costos originales por ingrediente.
* Totales originales.
* Porcentaje objetivo original.

El botón existente **REINICIAR SIMULACIÓN** debe restaurar exactamente esos valores.

La simulación debe continuar siendo local:

* No crear endpoints de escritura.
* No modificar `bar_detalle_combo_bar`.
* No modificar recetas.
* No actualizar WAC.
* No guardar cantidades simuladas.
* No enviar cambios a otros dispositivos.

# Preparación para la tarea de opcionales

Aunque esta tarea no corregirá todavía su agregación, conserva en el contrato de datos:

```text
ind_tipo_producto
tipo_parte_combo
```

No elimines, ignores ni sobrescribas estos campos, porque serán necesarios para distinguir ingredientes `PRINCIPAL` y `OPCIONAL` en la siguiente tarea.

No agregues una prueba que considere correcto sumar todos los opcionales. En particular, no congeles como resultado válido el costo de Bs 7,13 del Chuflay, porque ese cálculo será corregido en la siguiente tarea.

La refactorización no debe empeorar ni ocultar el problema existente de opcionales.

# Casos de aceptación

## V Long Island Iced Tea

Debe mostrarse:

```text
Jarana Silver:    1 OZ
Hiram Walker:     1 OZ
Roskoff:          1 OZ
37 Lenguas:       1 OZ
Triple Sec:       1 OZ
Coca-Cola:        4 OZ
```

Con las cantidades originales, el cálculo debe continuar produciendo aproximadamente:

```text
Costo:     Bs 13,83
Precio:    Bs 55,00
Pour cost: 25,15 %
```

Para 37 LENGUAS:

```text
Cantidad visible: 1 OZ
Rendimiento:       34 OZ
WAC:               Bs 80

COGS:
(1 / 34) × 80 = Bs 2,35 aproximadamente
```

Al aumentar a `1,5 OZ`:

```text
(1,5 / 34) × 80 = Bs 3,53 aproximadamente
```

## V Chuflay

Debe mostrarse:

```text
Casa Real Negra: 1,5 OZ
Sprite:           4 OZ
Ginger Ale:       4 OZ
Agua Tónica:      4 OZ
Agua sin gas:     4 OZ
```

Las fracciones deben permanecer internas:

```text
Casa Real Negra: 1,5 / 34
Sprite:           4 / 101,5
Ginger Ale:       4 / 67,5
Agua Tónica:      4 / 34
Agua sin gas:     4 / 67,5
```

Esta tarea no debe considerar Bs 7,13 como una validación semántica del costo del Chuflay.

# Precisión y validaciones

* Utiliza operaciones decimales para los cálculos monetarios.
* Evita redondear valores intermedios.
* Presenta importes con dos decimales.
* Presenta cantidades de forma legible, sin seis decimales innecesarios.
* Valida divisiones entre cero.
* Valida valores vacíos, negativos o no numéricos.
* Evita agregar dependencias nuevas sin justificación.
* Mantén el diseño responsive.
* Verifica que no exista desbordamiento horizontal.

# Trabajo solicitado

1. Inspecciona el flujo desde las vistas hasta el modal.
2. Identifica qué campo alimenta actualmente `CANT.`.
3. Confirma que corresponde a `cantidad_unidad_base` o a una conversión equivalente.
4. Ajusta el contrato de datos si es necesario para exponer claramente ambas cantidades.
5. Muestra y permite editar `cantidad_receta`.
6. Mantén `cantidad_unidad_base` como valor interno de costeo.
7. Implementa los controles `[−] [cantidad] [+]`.
8. Mejora la presentación del envase y rendimiento.
9. Conserva `tipo_parte_combo` en el contrato.
10. Agrega o actualiza las pruebas unitarias.
11. Ejecuta las validaciones disponibles.
12. Revisa el resultado en escritorio y móvil.
13. Actualiza `pourcost.md`.
14. Entrega un resumen de archivos modificados, fórmulas, pruebas y resultados.

Antes de implementar, presenta un diagnóstico breve de cómo fluye actualmente la cantidad desde MySQL hasta el campo `CANT.`. Si los nombres reales de los campos difieren, adapta la solución manteniendo esta separación semántica.
