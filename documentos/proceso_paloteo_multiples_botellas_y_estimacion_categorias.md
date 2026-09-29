# Proceso de Paloteo: Múltiples Botellas, Modelos de Envase y Estimación por Categorías

Este documento resume el funcionamiento del registro de inventario físico (paloteo) cuando se pesan múltiples botellas abiertas de un mismo producto, la gestión y pesaje con **diferentes modelos de botella** (perfiles de pesaje), así como la diferenciación técnica y operativa en el tratamiento de las categorías **VINOS** y **MEZCLADORES**.

---

## 1. Pesaje de Diferentes Modelos de Botella (Perfiles de Pesaje)

Un mismo producto en catálogo (por ejemplo, *Whisky 750 ml* o *Tequila 750 ml*) puede presentarse físicamente en diferentes contenedores debido a ediciones especiales, botellas promocionales o cambios del fabricante en el grosor del cristal. Aunque el volumen útil es idéntico, su **peso bruto** (botella llena) y su **tara** (botella vacía) son distintos.

### 1.1. Configuración de Modelos de Botella (Módulo PESAJE)

- **Tabla de Configuración (`app_producto_pesaje_config_api`):** Permite registrar múltiples perfiles activos (`estado = 'HAB'`) para un solo producto (`id_producto_almacen`), diferenciados por la columna `nombre_perfil`.
- **Perfil Estándar:** El primer modelo de un producto se registra con el nombre `Estándar`. Si existen variantes físicas, se pueden crear modelos adicionales con nombres libres (ejemplo: *Vidrio Grueso*, *Edición Conmemorativa*, *Envase Ancho*).
- **Parámetros por Modelo:** Cada perfil guarda de forma independiente:
  - `peso_bruto`: Peso total en gramos de la botella completamente llena.
  - `tara`: Peso en gramos de la botella totalmente vacía.
  - `gramos_por_oz`: Factor para convertir gramos de líquido a onzas. **No lo ingresa el usuario**: lo calcula el backend al crear o editar el modelo (`POST /api/pesaje/perfiles`, `PUT /api/pesaje/config/{id}`) como $\frac{\text{peso\_bruto} - \text{tara}}{\text{alm\_producto.cantidad\_detalle}}$. En la PWA se muestra como campo de solo lectura. En VINOS se fuerza a `1`.
  - `barcode`: Código de barras opcional. **Hoy se guarda y se edita, pero ninguna funcionalidad lo usa** (no hay escaneo, búsqueda ni selección automática de modelo por código de barras). Si se crea un modelo sin código, el backend le copia el de otro modelo activo del mismo producto, así que tampoco sirve hoy para distinguir modelos entre sí.

#### Limitación actual: todos los modelos se calculan con el volumen del producto

El denominador de `gramos_por_oz` es **siempre** el volumen del producto (`alm_producto.cantidad_detalle`), no el del envase físico del modelo. El sistema asume implícitamente que $\text{volumen\_modelo} = \text{volumen\_producto}$.

Mientras el modelo tenga el mismo volumen que el producto (el caso para el que se diseñó: mismo contenido en distinto vidrio), el cálculo es correcto. Si se registra como modelo un envase de **otro volumen**, `gramos_por_oz` queda mal y todas las capturas con ese modelo salen escaladas. Ejemplo: una botella de 750 ml (bruto 1242 g, tara 522 g, 25,5 oz reales) cargada como modelo de `BRANCA 1LT` (34 oz) da $720 / 34 = 21{,}18$ g/oz en vez de $720 / 25{,}5 = 28{,}24$, y una botella llena se leería como 34 oz. La validación de capacidad por botella (§2.3) tampoco se ajusta, porque también usa el volumen del producto.

Este caso es real en la operación (traspasos manuales del POS entre presentaciones del mismo líquido) y está en análisis en `TODO.md` ("Modelos de botella con volumen distinto al del producto"). Hasta que se resuelva, **no registres como modelo un envase de volumen distinto al del producto**.

### 1.2. Agrupación y Exposición en API (`/api/inventario/pendientes`)

En la respuesta JSON de los productos pendientes de conteo, FastAPI agrupa todos los modelos de botella activos de un producto dentro del arreglo `perfiles`:

```json
{
  "id_producto": 101,
  "nombre": "WHISKY 750 ML",
  "pesable": 1,
  "onzas_por_botella_llena": 25.36,
  "perfiles": [
    {
      "id": 12,
      "nombre_perfil": "Estándar",
      "peso_bruto": 1250.0,
      "tara": 500.0,
      "gramos_por_oz": 29.57
    },
    {
      "id": 18,
      "nombre_perfil": "Edición Especial Vidrio Grueso",
      "peso_bruto": 1380.0,
      "tara": 630.0,
      "gramos_por_oz": 29.57
    }
  ]
}
```

---

## 2. Paloteo con Múltiples Botellas y Distintos Modelos

Cuando el usuario realiza el conteo en barra y encuentra una o varias botellas abiertas del mismo producto:

### 2.1. Captura en Interfaz (Frontend)

- **Añadir Botellas:** Mediante el control `+ Botella` / `Añadir Botella`, el usuario agrega una fila por cada botella abierta que necesita pesar.
- **Selección de Modelo Específico:** Si el producto cuenta con más de un perfil activo, la PWA muestra automáticamente un combo desplegable (`<select>`) en esa fila. El barman selecciona el modelo físico exacto de la botella que tiene sobre la balanza.
- **Eliminación de Filas:** Se puede remover cualquier campo de botella añadido por error mediante el botón de eliminación (`close`), recalculando automáticamente los totales del producto.

### 2.2. Cálculo de Peso Líquido y Conversión Individual

Para cada botella registrada en el payload (`pesos_abiertas: [{peso, perfil_id, perfil_index}]`), el backend resuelve el perfil seleccionado buscando primero por `perfil_id`; si no lo encuentra, usa `perfil_index` sobre los perfiles `pesable=1` del producto ordenados por `id`. Si no resuelve ninguno, responde `400`. Luego aplica los parámetros de ese perfil:

1. **Perfil completo:** si al perfil le falta `tara` o tiene `peso_bruto`/`gramos_por_oz` nulos o en `0`, responde `400` (salvo VINOS).
2. **Validación de Peso Bruto:** el peso registrado no puede exceder el peso bruto de dicho modelo ($\text{peso\_medido} \le \text{peso\_bruto\_perfil}$); si lo excede, responde `400`.
3. **Obtención del Peso Líquido:**
   $$\text{peso\_líquido} = \max(0, \text{peso\_medido} - \text{tara\_perfil})$$
4. **Conversión a Onzas por Botella:**
   $$\text{onzas\_botella} = \frac{\text{peso\_líquido}}{\text{gramos\_por\_oz\_perfil}}$$

> **Validación pendiente — `peso ≥ tara − 10 g`:** esta validación todavía no está implementada y forma parte de la hoja de ruta del proyecto (ver `TODO.md`). Hoy el umbral existe en el código, pero una botella que pesa menos que `tara − 10 g` no genera error ni advertencia: se omite y aporta 0 oz al total.

### 2.3. Acumulación y Validaciones de Seguridad

- **Acumulación por Producto:** Las onzas obtenidas de cada botella (usando sus respectivos perfiles) se suman para determinar el líquido total abierto:
  $$\text{total\_onzas\_abiertas} = \sum \text{onzas\_botella}$$
- **Validación de Capacidad Máxima:** backend y frontend validan que las onzas de **cada botella** no superen `onzas_por_botella_llena` (el `cantidad_detalle` del producto, no del modelo); si las superan, el backend responde `400`.
- **Redondeo único:** el total exacto se redondea **una sola vez** a la grilla de 0,5 oz (`HALF_UP`), nunca botella por botella. Ver "Caso 3" en `documentos/redondeo_y_tolerancia.md`.
- **Sin límite de botellas:** no hay un máximo de botellas abiertas por producto.

### 2.4. Persistencia y Auditoría en Backend

Al enviar el paloteo (`POST /api/inventario/paloteo` o `PUT /api/inventario/paloteo/{id}`):

- **Auditoría Cruda (`app_paloteo_registro_crudo`):** tabla *append-only*. Se inserta **una fila por producto en cada envío** (registro o corrección), no una por botella. Cada fila guarda:
  - `botellas_cerradas`;
  - `pesos_abiertas`: JSON con la lista tal como llegó en el payload, `[{"peso", "perfil_id", "perfil_index"}]`;
  - `onzas_calculadas`: el **total exacto** del producto, sin redondear.

  **No se guardan** la tara, los gramos por onza ni las onzas **de cada botella**. Si después se edita un modelo, no se pueden reconstruir con exactitud las onzas por botella de un paloteo anterior. Los reportes no se ven afectados, porque usan el total `onzas_calculadas`. Guardar estos datos por botella está en `TODO.md`.
- **Consolidación POS (`bar_detalle_fisico`):** Se guardan las unidades cerradas y el total acumulado de onzas abiertas. Las onzas abiertas se redondean a la grilla operativa de media onza ($0.5\text{ oz}$) utilizando redondeo `HALF_UP`.
- **Corrección:** al reabrir un paloteo para corregirlo, la PWA restaura **todas** las botellas con su modelo desde la última fila cruda del producto. Solo en registros antiguos sin datos crudos reconstruye un único peso a partir de las onzas POS, usando el primer modelo.

---

## 3. Análisis de Categorías Especiales: VINOS vs MEZCLADORES

Surgió la interrogante de si la regla especial de la categoría **VINOS** aplica de la misma forma para la categoría **MEZCLADORES**.

### 3.1. Categoría VINOS (`id_categoria = 6`)

- **Naturaleza:** Es una **excepción técnica hardcodeada** en el backend Python (`main.py`).
- **Mecanismo:** Constantes fijas `TARA_VINOS = 0.0` y `GRAMOS_POR_OZ_VINOS = 1.0`.
- **Práctica Operativa:** El encargado en barra **no pesa la botella en la balanza**. Ingresa directamente una **estimación del contenido en copas disponibles**.

### 3.2. Categoría MEZCLADORES (`id_categoria = 22`)

- **Naturaleza:** Funciona a través de la **fórmula estándar de pesaje**, pero configurada en la base de datos con parámetros específicos.
- **Mecanismo:** En `app_producto_pesaje_config_api`, los productos de esta categoría (Coca-Cola, Sprite, Ginger Ale, Aguas, etc.) tienen asignados:
  - $\text{tara} = 0.0$
  - $\text{gramos\_por\_oz} = 1.0$
  - $\text{peso\_bruto} = \text{capacidad en onzas}$ (ej. $34\text{ oz}$ para 1L, $67.5\text{ oz}$ para 2L, $101.5\text{ oz}$ para 3L).
- **Práctica Operativa:** Al igual que en vinos, el encargado **no pesa las botellas de gaseosa/agua en la balanza**. Realiza una **estimación visual del sobrante**, pero expresada directamente en **onzas**.

### 3.3. Cuadro Comparativo Técnico y Operativo

| Criterio | Categoría VINOS (`id_categoria = 6`) | Categoría MEZCLADORES (`id_categoria = 22`) | Licores Estándar (Destilados, etc.) |
|---|---|---|---|
| **Uso de Balanza** | No (Estimación visual) | No (Estimación visual) | Sí (Pesaje en gramos con balanza) |
| **Soporte Múltiples Modelos** | No requiere (mismo valor fijo) | No requiere (parámetros $0$ y $1$) | Sí (Diferentes taras/pesos brutos por modelo) |
| **Unidad Ingresada** | Copas | Onzas | Gramos ($g$) |
| **Configuración Tara** | $0.0$ (forzada en código) | $0.0$ (configurada en BD) | Tara real de la botella en gramos |
| **Gramos por Onza** | $1.0$ (forzado en código) | $1.0$ (configurado en BD) | Factor real según densidad/envase |
| **Implementación Técnica** | Rama condicional explícita en Python (`es_vino`) | Pasa por el flujo general de pesaje usando datos de BD | Flujo general de pesaje |

---

## 4. Conclusión

1. **Gestión de Modelos de Botella:** El sistema permite configurar y seleccionar múltiples modelos de botella para un mismo producto. Cada pesaje utiliza la tara, el peso bruto y los gramos por onza del modelo seleccionado en la interfaz. Hoy todos los modelos deben tener el mismo volumen que el producto (ver la limitación en §1.1).
2. **Múltiples Botellas:** Se pueden registrar tantas botellas abiertas como existan en barra, combinando si es necesario distintos modelos de envase en un mismo conteo. Se conservan el peso y el modelo de cada botella, junto con el total exacto, antes de consolidar el total redondeado en el POS.
3. **Estimación en Vinos y Mezcladores:** En ambas categorías la práctica real de trabajo consiste en estimar el sobrante en lugar de pesar en balanza. La diferencia radica en la unidad utilizada por el personal (copas en **Vinos** vs. onzas en **Mezcladores**) y en la forma técnica de implementación (código hardcodeado en Vinos vs. datos de configuración en BD para Mezcladores).
