## Descripción del proceso de paloteo y ajustes de inventario

El propósito de esta PWA es controlar, comparar e igualar los dos tipos de inventario que forman parte de la lógica operativa de BackStage: el **inventario ideal** y el **inventario real**.

El **inventario ideal** es el inventario calculado automáticamente por el sistema POS. Este inventario se actualiza cada vez que se registra una comanda, descontando de la tabla `bar_inventario` las cantidades consumidas o vendidas de cada producto. En otras palabras, el POS mantiene una existencia teórica de lo que debería haber en barra: cuántas botellas cerradas existen y cuántas onzas quedan disponibles en las botellas abiertas.

El **inventario real**, en cambio, es el inventario físico que efectivamente existe en la barra. Este se obtiene mediante el conteo de botellas cerradas y el pesaje de botellas abiertas. Nuestra PWA permite registrar esas cantidades desde fuera del POS, convertir el peso de las botellas abiertas a onzas y construir una fotografía real del inventario existente al momento del paloteo.

Una vez registrado el inventario físico, la PWA compara ambos valores:

```text
Inventario real - Inventario ideal = Diferencia
```

Esta comparación se realiza por producto y separando dos dimensiones:

```text
Diferencia en botellas cerradas = botellas reales - botellas ideales
Diferencia en onzas abiertas    = onzas reales - onzas ideales
```

En un escenario perfecto, el inventario ideal y el inventario real deberían coincidir. Sin embargo, en la operación de un bar existen muchos factores que pueden generar diferencias: errores de comanda, derrames, roturas, cortesías no registradas, medidas mal servidas, productos usados sin comandar, errores de conteo, traspasos no registrados o pérdidas no justificadas.

Por ejemplo, supongamos que para el producto A el inventario ideal indica:

```text
3 botellas cerradas
5 onzas en botella abierta
```

Pero el inventario real registrado en barra indica:

```text
2 botellas cerradas
7 onzas en botella abierta
```

La diferencia sería:

```text
2 - 3 = -1 botella
7 - 5 = +2 onzas
```

Esto significa que falta una botella cerrada, pero sobran dos onzas en la botella abierta. Operativamente, después de revisar y justificar la causa de la diferencia, corresponde registrar en el POS:

```text
Salida por ajuste: 1 botella del producto A
Ingreso por ajuste: 2 onzas del producto A
```

De esta manera, el sistema corrige el inventario ideal para que coincida con el inventario real. Es decir, el inventario que vive en `bar_inventario` queda igualado con lo que físicamente existe en la barra.

## Por qué igualamos el inventario antes de abrir la siguiente operativa

La razón principal para realizar este proceso antes de abrir una nueva operativa es que la siguiente jornada debe comenzar con una base de inventario correcta.

`bar_inventario` representa el stock vivo con el que trabaja el POS. Si esa tabla queda con cantidades incorrectas, la siguiente operativa arranca desde una realidad falsa. El sistema podría creer que existen botellas que físicamente ya no están en barra, o podría asumir que faltan productos que en realidad sí existen. En ambos casos, las ventas, los consumos, las reposiciones, los reportes y los controles posteriores quedarían contaminados desde el inicio.

Por eso, el cierre de una operativa no debe limitarse a contar dinero o revisar comandas. También debe cerrar correctamente el inventario. El paloteo permite detectar las diferencias; el módulo de ajustes permite corregirlas; y la actualización de `bar_inventario` permite que la siguiente operativa empiece desde la existencia real.

Este punto es crítico porque las diferencias no corregidas se arrastran. Si hoy falta una botella y no se registra el ajuste, mañana el sistema seguirá trabajando como si esa botella existiera. Luego, cuando vuelva a aparecer una diferencia, ya no será claro si corresponde a la operativa actual, a la anterior o a una acumulación de errores de varios días. Mientras más tiempo se deja viva una diferencia, más difícil se vuelve identificar su causa.

Igualar el inventario ideal con el inventario real antes de la siguiente operativa permite hacer un corte limpio. Cada jornada empieza con cantidades verificadas, y cualquier nueva diferencia detectada puede atribuirse con mayor precisión a lo ocurrido durante esa operativa específica.

También es importante aclarar que ajustar el inventario no significa ocultar el problema. Al contrario, el proceso debe dejar evidencia de la diferencia encontrada, de los movimientos generados y del usuario que los confirmó. El objetivo no es borrar el descuadre, sino registrarlo, analizarlo y corregir el inventario para que el negocio pueda seguir operando con datos confiables.

En ese sentido, el ajuste cumple dos funciones al mismo tiempo:

```text
1. Corrige el inventario vivo del POS.
2. Conserva la trazabilidad de la diferencia detectada.
```

La primera función permite operar correctamente. La segunda permite auditar, identificar causas y tomar decisiones.

Actualmente hemos logrado que la PWA, a partir de las cantidades y pesos registrados durante el paloteo, sea capaz de calcular automáticamente las diferencias entre el inventario real y el inventario ideal. Luego, mediante el módulo de **Ajustes**, esas diferencias pueden convertirse en movimientos de ingreso o salida por ajuste, permitiendo igualar el inventario del POS con la realidad física de la barra.

Esta funcionalidad convierte a la PWA en una herramienta de control interno y auditoría operativa. No solo permite corregir inventario, sino también identificar patrones, prevenir pérdidas y tomar decisiones basadas en evidencia.

La finalidad no es simplemente “cuadrar números”, sino entender por qué se producen las diferencias. Si falta una botella porque un mesero tropezó, la botella cayó y se rompió, la solución puede ser mejorar el procedimiento de traslado, usar bandejas más seguras o ajustar la logística de servicio. Pero si falta una botella porque fue vendida sin comanda, entonces el problema ya no es operativo: es disciplinario, económico y de control interno.

Por eso, el proceso de paloteo y ajuste debe entenderse como un mecanismo de mejora continua. Las diferencias justificadas ayudan a mejorar procesos; las diferencias no justificadas ayudan a detectar pérdidas, responsabilidades y puntos débiles en la operación.

En resumen, buscamos igualar el inventario ideal con el inventario real antes de abrir la siguiente operativa porque el sistema debe comenzar cada jornada alineado con la realidad física de la barra. El inventario ideal sirve para controlar lo que debería existir; el inventario real confirma lo que efectivamente existe. Cuando ambos no coinciden, la diferencia debe registrarse, analizarse y ajustarse para que la siguiente operativa no herede errores de la anterior.
