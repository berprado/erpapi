---
description: "Corrección del cálculo del pour cost con ingredientes opcionales en la ventana modal"
name: "Pour Cost Modal Fix"
applyTo: "**"
---

### Contexto del problema

Actualmente, el costo y el pour cost parecen calcularse sumando todos los ingredientes registrados en la receta, incluidos todos los ingredientes opcionales.

Este comportamiento es incorrecto.

El costo de un cóctel debe calcularse utilizando:

1. Todos los ingredientes principales u obligatorios de la receta.
2. Únicamente los ingredientes opcionales seleccionados por el usuario.
3. Ningún ingrediente opcional que no esté seleccionado.

La regla general debe ser:

```text
Costo total =
Σ costo de ingredientes principales
+
Σ costo de ingredientes opcionales seleccionados
```

```text
Pour cost (%) =
(Costo total / Precio de venta) × 100
```

Antes de implementar, inspecciona la estructura actual del frontend, el backend y la respuesta utilizada para construir la receta. El campo que diferencia ingredientes principales y opcionales es `tipo_parte_combo` de la vista `vw_pourcost_receta` (valores `PRINCIPAL`, `OPCIONAL` o equivalentes). No determinar el tipo por nombre, categoría, posición ni orden visual.

### Ejemplo de referencia

En la captura adjunta, la receta de `V CHUFLAY` contiene:

* `CASA REAL NEGRA 1LT`: ingrediente principal y obligatorio.
* `AGUA S-GAS 2LT`: ingrediente opcional.
* `AGUA TONICA 1LT`: ingrediente opcional.
* `GINGER ALE 2LT`: ingrediente opcional.
* `SPRITE 3LT`: ingrediente opcional.

Al abrir la ventana modal, ningún ingrediente opcional debe estar seleccionado. Por tanto, el costo inicial debe considerar solamente `CASA REAL NEGRA 1LT`.

Tomando los datos visibles en la captura:

```text
Cantidad utilizada: 1,5 oz
WAC del envase: 100 Bs
Rendimiento: 34 oz

Costo de CASA REAL NEGRA =
1,5 × (100 / 34)
= 4,411764...
```

Resultado inicial esperado (`35,00 Bs` precio de venta):

```text
COSTO: 4,41 Bs
POUR COST: 12,61 %
```

Con todos los opcionales seleccionados:

```text
COSTO: 7,15 Bs
POUR COST: 20,43 %
```

Estos valores son el caso de prueba de referencia, válidos siempre que los datos cargados coincidan con la captura.

### Implementación previa (v11.4 — ya completado, no repetir)

Los siguientes puntos ya fueron implementados en la refactorización v11.4 y deben conservarse sin cambios:

* Selector `[−][cantidad][+]` por ingrediente.
* `cantidad_receta` como valor visible y editable; `cantidad_unidad_base` derivado internamente.
* `tipo_parte_combo` preservado en el estado local de simulación.
* Recálculo reactivo al cambiar cantidad o WAC de un ingrediente.
* Reiniciar simulación restaura valores originales del backend.

---

## Requerimientos funcionales

### 1. Cálculo inicial

Al abrir la ventana modal:

* Incluir automáticamente todos los ingredientes principales.
* Iniciar todos los ingredientes opcionales sin seleccionar.
* Calcular `COSTO` y `POUR COST` únicamente con los ingredientes principales.
* No modificar ni persistir la receta original.

Si una receta no contiene ingredientes opcionales, su comportamiento debe permanecer sin cambios.

### 2. Selección de ingredientes opcionales

Agregar un checkbox a cada ingrediente clasificado como opcional.

Los ingredientes principales:

* No deben tener checkbox.
* Deben incluirse siempre en el cálculo.
* No deben poder ser excluidos por el usuario.

Los checkboxes deben permitir seleccionar uno, varios o todos los ingredientes opcionales. No utilizar botones de opción, porque puede existir más de un ingrediente opcional válido al mismo tiempo.

La selección debe ser independiente para cada ingrediente. El tipo se determina exclusivamente por el campo `tipo_parte_combo` de la vista `vw_pourcost_receta` (valores `PRINCIPAL`, `OPCIONAL` o equivalentes). Como identificador estable del estado del checkbox, usar `id_producto` (es único por ingrediente en la receta tal como la expone la API actual). No utilizar el índice visual del arreglo.

### 3. Recálculo reactivo

Actualizar inmediatamente los siguientes valores cuando se marque o desmarque un ingrediente opcional:

* `COSTO`
* `POUR COST`
* Precio sugerido, si existe un porcentaje objetivo ingresado.
* Pour cost simulado, si existe un precio de venta simulado.

El recálculo también debe ejecutarse cuando cambie:

* La cantidad de un ingrediente incluido.
* El WAC de un ingrediente incluido.
* El precio utilizado en la simulación.

Si se modifica la cantidad o el WAC de un ingrediente opcional no seleccionado, el costo total no debe cambiar hasta que ese ingrediente sea seleccionado.

Centraliza esta lógica en una sola función o fuente de cálculo para evitar que el encabezado, el simulador y otros componentes produzcan resultados diferentes.

### 4. Estado temporal y reinicio

La selección de ingredientes opcionales forma parte de la simulación local:

* No debe modificar la receta almacenada.
* No debe persistirse en la base de datos.
* No debe convertir un ingrediente opcional en principal.
* No debe afectar otros cócteles o combos.

Al ejecutar `REINICIAR SIMULACIÓN`:

* Restaurar cantidades y valores WAC originales.
* Desmarcar todos los ingredientes opcionales.
* Recalcular utilizando únicamente los ingredientes principales.
* Limpiar los campos de simulación de precio y pour cost objetivo, manteniendo el comportamiento actual.

Al cerrar y volver a abrir la ventana modal, los opcionales también deben aparecer nuevamente desmarcados, salvo que la aplicación ya tenga una regla explícita y documentada para conservar temporalmente la simulación.

---

## Cambios en la interfaz

### 5. Identificación visual del tipo de ingrediente

Diferenciar claramente ingredientes principales y opcionales.

Cada tarjeta debe mostrar una etiqueta textual:

* `PRINCIPAL`
* `OPCIONAL`

Además:

* Los ingredientes principales deben tener un borde o fondo sutil basado en el color de acento verde de la interfaz.
* Los opcionales deben conservar un estilo neutro.
* No depender solamente del color para comunicar el tipo de ingrediente.
* Mantener contraste, legibilidad y coherencia con el diseño oscuro actual.

El checkbox de un opcional debe estar asociado de forma accesible con el nombre del ingrediente. Debe poder operarse mediante teclado.

### 6. Información de rendimiento

Mostrar únicamente el rendimiento del envase, abreviado como `REND:`:

```text
REND: 34 OZ.
```

Eliminar el bloque de envase (`ENVASE: X ML`) porque el volumen ya está incluído normalmente en el nombre del producto. Conservar el formato y las reglas actuales para representar valores decimales.

### 7. Etiqueta `CANT.` con unidad

La etiqueta del campo de cantidad debe incluir la unidad de la receta del ingrediente, centrada sobre el campo numérico:

```text
  CANT. OZ
[−]  [1,5]  [+]
```

La unidad cambia según el ingrediente: `CANT. OZ`, `CANT. COPA`, `CANT. UNID`, etc. Eliminar la etiqueta de unidad que actualmente aparece a la derecha del botón `[+]`, ya que `REND:` ya informa la unidad de la receta y repetirla genera redundancia visual.

Verifica que esta alineación funcione tanto en escritorio como en pantallas móviles y que no desplace el campo WAC.

### 8. Presentación del WAC

Mostrar el WAC con un máximo de dos decimales y sin ceros decimales innecesarios:

```text
6
9
100
18,58
```

No reducir la precisión almacenada en la base de datos. El redondeo debe afectar únicamente la presentación.

Los cálculos deben realizarse con la precisión numérica disponible y redondearse solamente al presentar el resultado final:

* `COSTO`: 2 decimales.
* `POUR COST`: 2 decimales.
* WAC visible: máximo 2 decimales.

Evitar cálculos con strings formateados. Mantener los valores internamente como números y aplicar el formato localizado únicamente al mostrarlos.

---

## Reglas de cálculo

Cuando la cantidad y el rendimiento estén normalizados en onzas, el costo del ingrediente debe calcularse como:

```text
Costo del ingrediente =
Cantidad utilizada en oz × (WAC del envase / Rendimiento del envase en oz)
```

Para otras unidades, reutiliza las conversiones y la lógica ya implementadas. No introduzcas una segunda fórmula incompatible ni asumas que todas las recetas siempre estarán expresadas en onzas.

Controlar estos casos:

* Precio de venta igual a cero o nulo.
* WAC nulo o inválido.
* Rendimiento igual a cero.
* Receta con varios ingredientes principales.
* Receta sin ingredientes opcionales.
* Receta que, por datos defectuosos, no tenga ningún ingrediente principal.

No permitir divisiones entre cero, valores `NaN` ni porcentajes infinitos. Si el pour cost no puede calcularse, mostrar `—` o el tratamiento visual ya utilizado por la aplicación y registrar claramente la causa.

---

## Criterios de aceptación

El caso de prueba principal es `V CHUFLAY` (ver ejemplo de referencia en el contexto). Los valores esperados son los documentados allí: `4,41 Bs` / `12,61 %` inicial; `7,15 Bs` / `20,43 %` con todos los opcionales seleccionados.

Además:

1. Al seleccionar un opcional, su costo se suma inmediatamente.
2. Al desmarcarlo, su costo se elimina inmediatamente.
3. Es posible seleccionar varios opcionales simultáneamente.
4. Cambiar cantidad o WAC de un opcional no seleccionado no modifica el total.
5. Al seleccionar posteriormente ese ingrediente, se utiliza su cantidad y WAC actuales.
6. Los ingredientes principales nunca pueden excluirse.
7. Reiniciar la simulación restaura valores originales y desmarca todos los opcionales.
8. Cerrar y reabrir el modal inicia una simulación limpia.
9. Los cócteles sin ingredientes opcionales mantienen su comportamiento.
10. La selección no modifica la base de datos ni la receta original.
11. El diseño funciona correctamente en escritorio y móvil.
12. No aparecen errores de división entre cero, `NaN` o `Infinity`.

---

## Pruebas requeridas

Cubrir como mínimo los siguientes escenarios (los del ejemplo V CHUFLAY son la referencia principal):

* Receta con un principal y varios opcionales (caso Chuflay).
* Receta con varios principales.
* Receta sin ingredientes opcionales.
* Selección, deseleción y selección simultánea de opcionales.
* Cambio de cantidad y WAC en opcional no seleccionado (el total no debe cambiar).
* Reinicio de simulación y reapertura del modal.
* Precio de venta igual a cero y rendimiento inválido o igual a cero.
* Formato visual del WAC (máximo 2 decimales sin ceros innecesarios).

Ejecuta las pruebas, el linter y el proceso de compilación disponible en el proyecto.

Al finalizar, informa:

1. La causa técnica del cálculo incorrecto.
2. Los archivos modificados.
3. La fuente de datos utilizada para distinguir `PRINCIPAL` de `OPCIONAL`.
4. La fórmula o función central utilizada para recalcular.
5. Las pruebas ejecutadas y sus resultados.
6. Cualquier supuesto o limitación encontrada.

Evita refactorizaciones no relacionadas con este requerimiento y conserva el estilo visual, la arquitectura y las convenciones actuales del proyecto.
