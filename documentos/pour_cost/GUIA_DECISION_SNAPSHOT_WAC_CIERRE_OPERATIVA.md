# Guía de decisión e implementación del snapshot WAC al cierre de operativa

**Sistema:** POS BackStage / Motor Financiero V9  
**Base de datos:** MySQL 5.6.12  
**Decisión recomendada:** Opción B — congelamiento del WAC al cierre definitivo de la operativa  
**Fecha:** 2026-07-14  
**Estado:** Guía de decisión y base funcional para implementación

---

## 1. Propósito

Esta guía explica por qué se recomienda congelar el WAC al cierre definitivo de cada operativa y por qué no se recomienda congelarlo al cierre individual de cada comanda en el contexto actual de BackStage.

También define las condiciones funcionales y técnicas necesarias para implementar la opción elegida de manera:

- consistente;
- auditable;
- idempotente;
- resistente a fallos;
- compatible con el POS legacy;
- alineada con el motor financiero V9;
- adecuada para análisis histórico de COGS, margen y *pour cost*.

---

## 2. Contexto financiero

BackStage utiliza como costo operativo vigente:

> **WAC Perpetuo Móvil con corte estratégico por inflación y mantenimiento mediante caché de costo.**

El WAC vigente se guarda por producto y almacén en:

```sql
cache_wac_producto
```

y se actualiza incrementalmente cuando se insertan nuevos ingresos de almacén mediante:

```sql
trg_wac_after_insert_detalle
```

El motor V9 utiliza ese costo para valorizar el consumo real de productos e ingredientes:

```text
cantidad consumida en unidad base × WAC vigente = COGS
```

Como el WAC cambia con las nuevas compras, se necesita congelar el costo aplicable a las operaciones cerradas. De lo contrario, un reporte histórico podría cambiar cada vez que cambie `cache_wac_producto`.

---

## 3. Alternativas evaluadas

### 3.1 Opción A — Snapshot al cierre de cada comanda

Cada comanda se valoriza con el WAC existente en el momento exacto en que se paga o cierra.

```text
Comanda cerrada
    → leer WAC vigente
    → calcular COGS
    → guardar snapshot
```

### 3.2 Opción B — Snapshot al cierre de la operativa

Cuando la operativa se cierra definitivamente, se congela un WAC por producto y almacén. Todas las comandas y consumos válidos de esa jornada se valorizan con ese conjunto de costos.

```text
Operativa cerrada
    → congelar WAC por producto
    → valorizar todas las comandas
    → validar cobertura
    → cerrar financieramente
```

---

## 4. Decisión recomendada

Se recomienda adoptar la **Opción B**:

> BackStage congelará el WAC por producto y almacén al cierre definitivo de cada operativa. Todas las comandas y consumos válidos pertenecientes a esa operativa se valorizarán utilizando ese WAC.

La unidad de cierre financiero será:

```text
id_operacion
```

La unidad de costo congelado será:

```text
id_operacion + id_almacen + id_producto
```

No se trata de un único costo general para toda la jornada. Cada producto conserva su propio WAC, pero ese WAC será uniforme dentro de la operativa.

---

## 5. Motivos para elegir la Opción B

### 5.1 Coincide con la unidad natural de gestión de BackStage

BackStage organiza su actividad mediante operativas con estados definidos:

| Estado | Significado |
|---:|---|
| 22 | EN PROCESO |
| 24 | INICIO DE CIERRE |
| 23 | CERRADO |

La operativa ya agrupa:

- ventas;
- consumos;
- cortesías;
- conciliación;
- inventario físico;
- ajustes;
- cierre de caja;
- indicadores de rentabilidad.

Utilizar la misma unidad para cerrar costos mantiene alineados inventario, ventas y finanzas.

### 5.2 Produce indicadores homogéneos por jornada

Todas las unidades consumidas de un producto dentro de una misma operativa se valorizan con el mismo WAC.

Esto facilita comparar:

- COGS entre operativas;
- margen por jornada;
- *pour cost* diario;
- consumo por categoría;
- desempeño por artículo vendido;
- diferencias entre costo teórico y real.

Con la Opción A, un mismo producto podría tener varios costos dentro de una sola jornada, dificultando explicar el resultado total.

### 5.3 Simplifica la auditoría

La pregunta de auditoría se vuelve concreta:

> ¿Qué WAC se aprobó para el producto X en la operativa Y?

La respuesta debe encontrarse en una única fila identificada por:

```text
id_operacion + id_almacen + id_producto
```

Con la Opción A habría que reconstruir el WAC utilizado en cada comanda y relacionarlo con la secuencia exacta de cierres y compras.

### 5.4 Reduce la complejidad técnica

La Opción B evita incorporar lógica financiera pesada en cada cierre de comanda, una operación crítica y frecuente del POS.

Esto disminuye:

- carga transaccional durante la atención al cliente;
- dependencia de triggers adicionales sobre comandas;
- riesgo de que una falla financiera interrumpa el cobro;
- cantidad de lecturas y escrituras de costos;
- complejidad de reintentos.

### 5.5 Se adapta mejor al registro real de compras

En un negocio operativo, la recepción física, la factura del proveedor y el registro en el sistema no siempre ocurren simultáneamente.

Congelar cada comanda con precisión de minutos puede producir una falsa sensación de exactitud si los ingresos de almacén se registran con retraso. El cierre de operativa proporciona una ventana para completar y validar los movimientos que deben afectar la jornada.

### 5.6 Facilita la detección de inconsistencias antes del cierre financiero

Durante `24 INICIO DE CIERRE` se puede validar:

- comandas aún abiertas;
- productos consumidos sin WAC;
- ingresos pendientes;
- costos extremos;
- bonificaciones sin justificar;
- diferencias de inventario;
- consumos sin producto asociado;
- duplicidades o líneas incompletas.

La Opción A congela costos mientras la jornada sigue activa, antes de disponer de esta revisión integral.

### 5.7 Facilita reintentos atómicos

Una operativa completa puede procesarse dentro de una transacción:

```text
todo el snapshot se confirma
o
ningún dato queda confirmado
```

Esto es más seguro que cientos de snapshots independientes que pueden quedar repartidos entre éxitos, fallos y reintentos.

### 5.8 Es compatible con MySQL 5.6 y el POS legacy

La implementación puede realizarse mediante tablas analíticas nuevas y un proceso externo controlado, sin modificar las tablas históricas del POS ni introducir dependencias incompatibles con MySQL 5.6.

---

## 6. Motivos para descartar la Opción A en BackStage

La Opción A no es incorrecta en términos generales. Se descarta porque no ofrece una ventaja suficiente frente a su complejidad y a las características operativas actuales de BackStage.

### 6.1 Precisión aparente si las compras se registran tarde

La opción promete usar el costo exacto al momento de la venta, pero esa exactitud solo existe si cada compra se registra inmediatamente cuando el producto ingresa físicamente.

Si una compra llega a las 15:00 y se registra al día siguiente, todas las comandas cerradas durante la noche conservarán un WAC desactualizado.

El sistema sería exacto respecto a la base de datos, pero no necesariamente respecto a la realidad económica.

### 6.2 Aumenta el trabajo durante una operación crítica

El cierre o pago de la comanda debe ser rápido y confiable. Agregar captura de costos, validaciones e inserciones históricas puede:

- aumentar el tiempo de respuesta;
- introducir bloqueos;
- afectar el cobro si falla la base de datos analítica;
- crear dependencias entre atención al cliente y procesamiento financiero.

### 6.3 Genera múltiples WAC para un producto dentro de una jornada

Si se registra una compra durante la operativa, las comandas anteriores y posteriores podrían tener costos diferentes para el mismo producto.

Esto es cronológicamente preciso, pero complica:

- explicación de márgenes diarios;
- conciliación con inventario;
- comparación entre productos;
- revisión de cortesías;
- reproducción manual de resultados.

### 6.4 Hace más complejas las correcciones

Una compra registrada o corregida tardíamente puede afectar solo determinadas comandas. Corregir el histórico exigiría identificar:

- qué comandas cerraron antes o después;
- qué WAC les correspondía;
- qué consumos deben recalcularse;
- cómo conservar la auditoría de valores anteriores.

### 6.5 Incrementa el volumen y la redundancia

El WAC se repetiría en cada línea de consumo de cada comanda, aunque muchas comandas consecutivas hayan utilizado exactamente el mismo costo.

La Opción B conserva una sola definición de costo por producto y operativa, y deriva de ella todos los COGS.

### 6.6 Requiere integración más invasiva con el POS

Para capturar realmente el instante de cierre sería necesario intervenir el flujo de pago de la comanda o añadir un mecanismo síncrono asociado a `estado_comanda = 26`.

Esa intervención aumenta el riesgo sobre un sistema legacy que actualmente cumple una función crítica.

### 6.7 Complica la idempotencia

Una comanda puede cerrarse, reintentarse, modificarse excepcionalmente o ser procesada por más de un servicio. Sin una clave y un protocolo estrictos podrían generarse:

- snapshots duplicados;
- líneas parciales;
- costos diferentes para el mismo cierre;
- reprocesamientos silenciosos.

### 6.8 No coincide con la forma principal de análisis

Los KPI V9 se consolidan fundamentalmente por `id_operacion`. La granularidad transaccional de la Opción A añade complejidad sin mejorar necesariamente las decisiones gerenciales que se toman por jornada.

---

## 7. Limitación aceptada de la Opción B

La Opción B aplica el WAC de cierre a toda la operativa, incluso a consumos ocurridos antes de una compra registrada durante esa misma jornada.

Ejemplo:

```text
19:00  Se vende producto con WAC vigente Bs 15
22:00  Una compra actualiza el WAC a Bs 18
04:00  Se cierra la operativa
```

Toda la operativa se valorizará a Bs 18 para ese producto.

Esto se acepta porque la prioridad es obtener:

- un costo de reposición homogéneo;
- una lectura gerencial consistente;
- una auditoría reproducible por operativa.

La Opción B no pretende reconstruir el costo exacto por minuto. Pretende establecer un costo oficial y defendible para la jornada.

---

## 8. Momento exacto del snapshot

La captura debe asociarse al cierre definitivo:

```text
24 INICIO DE CIERRE
        ↓
validaciones financieras
        ↓
23 CERRADO
        ↓
snapshot inmediato y controlado
```

No es suficiente ejecutar horas después un job que lea el WAC que exista en ese momento. Entre el cierre y la ejecución podría registrarse una compra correspondiente a otra jornada.

La regla debe ser:

> Se conserva el WAC vigente en el momento formal de cierre financiero de la operativa.

### 8.1 Cierre operativo y cierre financiero

Conviene distinguir:

- **Cierre operativo:** el POS termina la jornada y establece estado `23 CERRADO`.
- **Cierre financiero:** el motor valida, captura WAC y genera los COGS históricos.

No es necesario modificar la tabla legacy de estados. El estado financiero puede registrarse en una tabla analítica propia.

Estados sugeridos:

```text
PENDIENTE
PROCESANDO
COMPLETADO
ERROR
REQUIERE_REVISION
```

---

## 9. Arquitectura recomendada

### 9.1 Tabla de WAC por operativa

Se recomienda crear una tabla nueva, por ejemplo:

```sql
analytics_wac_operacion
```

Su responsabilidad será conservar el costo aprobado por producto y operativa.

Campos conceptuales:

```text
id
id_operacion
id_almacen
id_producto
wac_snapshot
fecha_snapshot
origen_wac
usuario_proceso
version_snapshot
estado
```

Restricción mínima:

```sql
UNIQUE (id_operacion, id_almacen, id_producto, version_snapshot)
```

Si no se manejarán versiones inicialmente:

```sql
UNIQUE (id_operacion, id_almacen, id_producto)
```

### 9.2 Tabla de COGS histórico

`analytics_cogs_historico` debe almacenar el resultado derivado del WAC congelado, no volver a consultar el caché dinámico.

Flujo:

```text
cache_wac_producto
        ↓ captura al cierre
analytics_wac_operacion
        ↓ valorización del consumo
analytics_cogs_historico
```

### 9.3 Tabla de control del proceso

Se recomienda registrar el estado del cierre financiero en una tabla como:

```sql
analytics_cierre_financiero
```

Campos conceptuales:

```text
id_operacion
estado_proceso
fecha_inicio
fecha_fin
cantidad_comandas
cantidad_productos
cantidad_lineas_cogs
productos_sin_wac
mensaje_error
usuario_proceso
version_snapshot
```

Esto permite saber si una operativa está totalmente procesada sin inferirlo a partir de la existencia de alguna fila histórica.

---

## 10. Granularidad recomendada

### 10.1 WAC congelado

Una fila por:

```text
operativa + almacén + producto
```

### 10.2 COGS histórico

La granularidad debe permitir reconstruir el costo del artículo vendido y del ingrediente consumido.

Se recomienda una fila por línea real de consumo, conservando al menos:

```text
id_operacion
id_comanda
id_detalle_comanda
id_producto
tipo_parte_combo
cantidad_consumida_unidad_base
costo_unitario_snapshot
cogs_total
version_snapshot
```

Si se decide consolidar por comanda y producto, debe documentarse explícitamente y aplicarse una clave única compatible. No conviene dejar una granularidad implícita.

---

## 11. Productos que deben congelarse

Se recomienda capturar el WAC de todos los productos con consumo válido en la operativa.

No se deben omitir silenciosamente productos sin caché. Deben aparecer como incidencias:

```text
producto consumido
+ sin WAC vigente
= cierre financiero requiere revisión
```

El sistema puede permitir excepcionalmente COGS cero, pero solo mediante una decisión explícita y auditada.

---

## 12. Validaciones previas al cierre financiero

Antes de generar snapshots deben comprobarse como mínimo:

### Operativa

- La operativa existe.
- Está en `24 INICIO DE CIERRE` o `23 CERRADO`, según el flujo aprobado.
- No existen comandas activas.
- No se permiten nuevas ventas ni anulaciones.
- La conciliación requerida está completa.

### Ingresos y WAC

- Los ingresos relevantes de almacén están registrados.
- No existen ingresos pendientes que deban afectar la jornada.
- No existen cantidades negativas.
- No existen costos negativos.
- Las bonificaciones con costo cero están justificadas.
- Los costos extremos fueron revisados.
- Todo producto consumido tiene WAC válido.
- No existe stock positivo sin WAC cacheado.

### Consumos

- Todas las comandas cerradas pertenecientes a la operativa están incluidas.
- Se incluyen ventas normales y cortesías.
- Se incluyen productos directos.
- Se incluyen componentes `PRINCIPAL` y `OPCIONAL` de combos.
- Las conversiones a unidad base no producen nulos ni divisiones por cero.
- No existen consumos sin `id_producto`.

### Integridad

- No existe un snapshot completo previo para la misma versión.
- No hay otro proceso trabajando sobre la misma operativa.
- Las tablas de destino están disponibles.
- El número esperado de comandas y consumos puede reconciliarse.

---

## 13. Proceso transaccional recomendado

El cierre financiero debe ser atómico.

```text
1. Adquirir bloqueo lógico por id_operacion
2. Marcar estado PROCESANDO
3. Iniciar transacción
4. Validar operativa y consumos
5. Capturar WAC por producto
6. Generar COGS histórico
7. Comparar cobertura esperada y obtenida
8. Guardar métricas de control
9. Confirmar transacción
10. Marcar estado COMPLETADO
```

Si cualquier paso falla:

```text
ROLLBACK
→ registrar ERROR
→ conservar mensaje y contexto
→ dejar la operativa disponible para reintento controlado
```

Nunca debe considerarse procesada una operativa únicamente porque exista al menos una fila en `analytics_cogs_historico`.

---

## 14. Idempotencia y reintentos

El proceso debe poder ejecutarse nuevamente sin duplicar resultados.

Requisitos:

- clave única para el WAC de la operativa;
- clave única o identificador estable para cada línea de COGS;
- control de estado por `id_operacion`;
- bloqueo contra dos ejecuciones simultáneas;
- transacción única por operativa;
- reintento solo después de un rollback completo o mediante nueva versión autorizada.

No debe utilizarse como único control:

```sql
id_comanda NOT IN (
    SELECT id_comanda FROM analytics_cogs_historico
)
```

Ese criterio puede ocultar comandas parcialmente procesadas.

---

## 15. Política para ingresos registrados tarde

Debe establecerse una hora o evento de corte para compras e ingresos relacionados con la operativa.

Regla recomendada:

> Antes del cierre financiero deben registrarse y validarse todos los ingresos que deban afectar el costo de reposición de la jornada.

Si un ingreso se registra después del cierre, no debe modificar silenciosamente el snapshot anterior.

Alternativas de corrección:

1. mantener el cierre original y reconocer el nuevo WAC desde la siguiente operativa;
2. generar una nueva versión del cierre financiero con autorización;
3. registrar un ajuste histórico separado, conservando antes y después;
4. reabrir excepcionalmente el cierre financiero mediante procedimiento formal.

La recomendación general es mantener el snapshot original y aplicar el cambio hacia adelante, salvo que el error sea material y exista autorización para una nueva versión.

---

## 16. Correcciones posteriores

No se deben sobrescribir snapshots históricos sin dejar evidencia.

Toda corrección debería registrar:

- operativa afectada;
- producto;
- valor anterior;
- valor corregido;
- motivo;
- usuario;
- fecha;
- documento o ingreso relacionado;
- versión del snapshot;
- impacto sobre COGS y margen.

Si se recalcula una operativa, los datos anteriores deben conservarse o quedar respaldados en una bitácora.

---

## 17. Cortesías

Las cortesías deben formar parte del snapshot porque representan consumo real.

Reglas:

- venta real: cero cuando corresponde;
- venta teórica: valor anterior a la cortesía;
- COGS: se calcula normalmente;
- margen real: disminuye por el costo consumido;
- margen teórico: permite medir el resultado sin la cortesía.

Excluir cortesías produciría un COGS artificialmente bajo.

---

## 18. Almacén de referencia

La implementación actual utiliza:

```sql
id_almacen = 1
```

Debe decidirse si esta es una regla permanente o una limitación temporal.

Si en el futuro existen varios almacenes que abastecen ventas, el origen del costo deberá determinarse explícitamente. No se debe asumir silenciosamente que todos los consumos pertenecen al almacén 1.

---

## 19. Monitoreo recomendado

El control del snapshot debe informar:

- última operativa procesada correctamente;
- fecha y duración del último proceso;
- operativas cerradas pendientes;
- operativas en error;
- comandas esperadas y procesadas;
- líneas de consumo esperadas y procesadas;
- productos sin WAC;
- costos iguales a cero;
- duplicados;
- snapshots parciales;
- versión vigente del cierre;
- diferencia entre COGS calculado y suma histórica almacenada.

`check_last_snapshot.php`, que solo muestra `MAX(fecha_snapshot)` y `COUNT(*)`, no es suficiente como control de integridad. Puede conservarse como comprobación rápida, pero debe complementarse.

---

## 20. Relación con el motor V9

Después de implementar la Opción B deben distinguirse dos lecturas:

| Uso | Fuente |
|---|---|
| Análisis dinámico con costo vigente | `comandas_v9_detallada` + `cache_wac_producto` |
| Análisis oficial de operativa cerrada | snapshot WAC + `analytics_cogs_historico` |

Las pantallas y reportes deben indicar cuál de las dos lecturas presentan.

Un KPI histórico oficial no debería consultar accidentalmente el caché actual, porque cambiaría cuando se registren nuevas compras.

---

## 21. Migración desde el job actual

El `snapshot_job.php` revisado no implementa todavía la Opción B porque:

- procesa comandas individualmente como pendientes;
- utiliza `vw_wac_producto_almacen`;
- congela el promedio histórico acumulado descartado;
- no captura el WAC móvil de `cache_wac_producto`;
- no utiliza una tabla de WAC por operativa;
- no usa una transacción común para combos y directos;
- puede dejar comandas parcialmente procesadas;
- no impide ejecuciones simultáneas;
- puede omitir productos sin costo debido a sus `INNER JOIN`.

Plan de migración recomendado:

1. definir y crear las tablas analíticas nuevas;
2. definir granularidad y claves únicas;
3. desarrollar el nuevo proceso por `id_operacion`;
4. utilizar el WAC vigente del caché al cierre;
5. incluir validaciones y transacción;
6. probar en `adminerp_copy`;
7. comparar resultados con V9 y con casos manuales;
8. ejecutar en paralelo sin afectar reportes oficiales;
9. aprobar resultados;
10. desactivar el job antiguo;
11. migrar reportes históricos;
12. retirar vistas heredadas sin dependencias.

---

## 22. Pruebas mínimas de aceptación

La implementación debe superar al menos estos escenarios:

1. Operativa con productos directos solamente.
2. Operativa con combos y componentes opcionales.
3. Operativa con cortesías.
4. Producto con WAC normal.
5. Producto con bonificación durante la jornada.
6. Producto sin WAC.
7. Producto con almacén en cero y nuevo ingreso.
8. Compra registrada durante la operativa.
9. Compra registrada después del cierre.
10. Fallo durante la generación de COGS.
11. Reintento después del fallo.
12. Dos ejecuciones simultáneas.
13. Operativa ya procesada.
14. Corrección autorizada mediante nueva versión.
15. Comparación entre suma de líneas históricas y KPI esperado.

Cada prueba debe documentar:

- datos iniciales;
- WAC esperado;
- consumo esperado;
- COGS esperado;
- filas generadas;
- estado final del proceso.

---

## 23. Condiciones que justificarían reconsiderar la Opción A

La decisión podría revisarse si en el futuro:

- todos los ingresos se registran en tiempo real;
- el POS expone un evento transaccional confiable de cierre de comanda;
- se necesita margen exacto por ticket y minuto;
- las compras cambian frecuentemente durante la jornada;
- el cierre por comanda no afecta el rendimiento;
- existe versionado y auditoría suficientes;
- una exigencia contable o gerencial requiere esa granularidad.

Mientras esas condiciones no existan, la Opción B ofrece mayor valor operativo y menor riesgo.

---

## 24. Regla oficial propuesta

> **BackStage utilizará el cierre de operativa como punto de corte financiero. Al finalizar definitivamente una operativa, el sistema congelará un WAC por producto y almacén y utilizará esos valores para calcular el COGS de todas las comandas, productos directos, ingredientes y cortesías pertenecientes a la jornada. El procesamiento será atómico, idempotente, auditable y separado de las tablas legacy del POS. Los cambios posteriores del WAC no modificarán el cierre histórico; cualquier corrección requerirá un procedimiento versionado y autorizado.**

---

## 25. Conclusión

La Opción A ofrece mayor precisión cronológica, pero depende de que las compras se registren oportunamente y exige una integración más invasiva con el cierre de comandas. En el contexto actual de BackStage, esa precisión puede ser más aparente que real.

La Opción B se alinea con la jornada operativa, simplifica la auditoría, produce KPI homogéneos, permite validaciones previas y reduce el riesgo sobre el POS legacy. Su principal concesión es que aplica el WAC final de la jornada a todos los consumos de la operativa, incluso si el costo cambió durante ella.

Esa concesión es aceptable siempre que:

- se defina claramente el momento de corte;
- los ingresos relevantes estén registrados antes del cierre financiero;
- el WAC se congele por producto y operativa;
- los COGS se deriven del snapshot y no del caché dinámico;
- el proceso sea transaccional y verificable;
- las correcciones posteriores queden auditadas.

Por estas razones, la Opción B es la alternativa recomendada para el motor financiero V9 de BackStage.
