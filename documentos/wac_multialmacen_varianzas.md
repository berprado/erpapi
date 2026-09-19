# Política de WAC multialmacén para varianzas de inventario

## Decisión

El WAC se mantiene de forma independiente por la clave:

```text
id_almacen + id_producto
```

No existe un WAC global único por producto. Una misma botella puede tener un
costo vigente distinto en cada almacén según sus propios ingresos, costos y
stock previos.

La futura valoración histórica de varianzas de barra debe congelar también el
almacén de costo usado. La clave de su snapshot será, como mínimo:

```text
id_operacion + id_barra + id_almacen + id_producto
```

Esto permite auditar tanto el monto de la diferencia como la fuente concreta
del WAC, y deja abierta una configuración futura de barra a almacén sin
reinterpretar registros históricos.

## Ejemplo durante una operativa

Si se reciben 10 botellas de ron a Bs 150 en el almacén 1 y, más tarde, 10
botellas del mismo ron a Bs 145 en el almacén 2, se actualizan dos costos
independientes:

```text
WAC almacén 1 = promedio ponderado de su stock previo y las 10 botellas a Bs 150
WAC almacén 2 = promedio ponderado de su stock previo y las 10 botellas a Bs 145
```

No corresponde promediar Bs 150 y Bs 145 entre almacenes, porque ello
atribuiría a cada almacén compras y existencias que no le pertenecen.

Una variación detectada en una barra se valoriza con el WAC del almacén que la
abastece. Mientras no exista una relación explícita barra-almacén, la PWA usa
la decisión operativa vigente de `id_almacen = 1`, guarda ese identificador en
el snapshot y no lo infiere desde `bar_barra`.

## Traspasos entre almacenes y barra

Un traspaso no recalcula el WAC del almacén origen. El costo que acompaña la
mercadería transferida debe estar definido explícitamente por el proceso POS:

- Si el almacén destino mantiene WAC propio, el traspaso debe registrar su
  costo de entrada de acuerdo con la regla financiera aprobada para ese destino.
- Si la barra no posee almacén contable propio, la variación de su inventario
  continúa valorándose con el almacén abastecedor configurado.
- La PWA no debe inferir ni modificar costos de traspaso, ni escribir en las
  tablas legacy del POS.

## Compatibilidad futura

Cuando se implemente una relación efectiva de barra a almacén, debe exponerse
en una fuente de configuración explícita y versionada. El módulo de ajustes
resolverá el almacén desde esa fuente antes de leer `cache_wac_producto`.

Los snapshots ya registrados conservan `id_almacen`, `wac_snapshot` y el
origen de valoración; por ello no deben recalcularse ni migrarse al cambiar la
configuración futura de una barra.

## Alcance

Esta decisión solo define la valoración de varianzas de inventario en la PWA.
No modifica `cache_wac_producto`, los ingresos, traspasos, ajustes ni ninguna
otra tabla legacy del POS.