---
name: style
description: Skill para el correcto manejo de tokens CSS relacionados con la línea gráfica BackStage. Esta guía muestra colores base, acentos de marca, colores semánticos, textos y radios recomendados para mantener la coherencia visual en los proyectos de BackStage entre los cuales se encuentra este proyecto.
---

## 1. Esencia de marca

**BackStage Karaoke & Bar** es una marca nocturna, musical, moderna y social. Su identidad visual se apoya en la estética de letrero neón: fondo oscuro, alto contraste, brillo controlado y dos colores protagonistas muy reconocibles: verde aqua neón y magenta neón.

La marca debe transmitir:

- Energía nocturna.
- Diversión elegante.
- Tecnología y modernidad.
- Música, escenario y experiencia compartida.
- Un ambiente premium, pero accesible.

La lógica visual principal es:

> Negro escenario + verde neón + magenta neón + composición limpia.

El neón debe sentirse como luz de escenario: intenso, memorable y bien dosificado. No debe convertirse en ruido visual.

---

## 2. Dos contextos visuales de la marca

La marca BackStage debe manejar dos sistemas relacionados, pero no idénticos:

1. **Contexto comercial / visible / branding**  
   Para web pública, menú, señalética, menú digital, material promocional, redes sociales, anuncios, invitaciones, table tents, pantallas, monitores, piezas impresas y contenido de alto impacto.

2. **Contexto ejecutivo / analítico / operativo**  
   Para dashboards, tablas, reportes, gráficos, infografías, organigramas, newsletters, presentaciones, reportes internos, PWA administrativa, indicadores de ventas, inventario, COGS, margen, reservas y métricas operativas.

Ambos contextos deben sentirse BackStage, pero con distinta intensidad visual.

---

# PARTE A — SISTEMA COMERCIAL / BRANDING

## 3. Paleta comercial principal

| Rol | Color | Hex |
|---|---:|---:|
| Negro escenario | Fondo principal | `#050505` |
| Negro suave | Fondos secundarios | `#111111` |
| Verde BackStage | Color principal | `#48E898` |
| Magenta Stage | Color protagonista/acento | `#E00078` |
| Blanco humo | Texto principal | `#F5F5F5` |
| Gris humo | Texto secundario | `#B8B8B8` |

## 4. Proporción recomendada en piezas comerciales

| Color | Proporción sugerida |
|---|---:|
| Negro / fondos oscuros | 55–65% |
| Blanco / gris para lectura | 15–20% |
| Verde neón | 10–15% |
| Magenta neón | 8–12% |
| Acentos secundarios | 0–5% |

El verde y el magenta no deben competir todo el tiempo. En cada pieza conviene definir un color dominante y otro de apoyo.

Ejemplo:

- Pieza institucional: verde dominante, magenta de acento.
- Evento musical o promo nocturna: magenta dominante, verde de contraste.
- Menú digital: verde para navegación/acción, magenta para destacados.

## 5. Colores secundarios comerciales

Estos colores pueden usarse para campañas específicas, no como reemplazo de la marca principal.

| Uso | Color | Hex |
|---|---:|---:|
| Azul eléctrico | Información, energía digital | `#00D1FF` |
| Morado neón | Eventos nocturnos, fiestas | `#7A00FF` |
| Dorado suave | VIP, premium, botellas, reservas especiales | `#C9A646` |

Recomendación: el dorado debe usarse con moderación para categorías premium. Si se usa demasiado, la marca puede alejarse del lenguaje neón moderno.

---

## 6. Uso del logo

### Versiones principales

1. **Logo horizontal completo**  
   Recomendado para web, encabezados, banners, fachadas, firmas, piezas panorámicas y contenido 16:9.

2. **Logo apilado / vertical**  
   Recomendado para stories, reels, afiches verticales, invitaciones, pantallas 9:16 y piezas con composición centrada.

3. **Isotipo circular**  
   Recomendado para avatar, favicon, stickers, sellos, iconos de app, botones, marca de agua, table tents y señalética reducida.

4. **Versión neón con glow**  
   Recomendado para piezas de alto impacto, pantallas, animaciones, videos, reels, promos nocturnas y ambientación digital.

### Reglas de uso

- Usar el logo preferentemente sobre fondo negro o fondos muy oscuros.
- No colocar el logo sobre fondos claros salvo que se use una versión específicamente adaptada.
- No alterar la proporción entre BACK y STAGE.
- No cambiar verde/magenta por otros colores en piezas institucionales.
- No aplicar sombras duras ni efectos 3D ajenos a la estética neón.
- No usar glow excesivo en formatos pequeños, porque pierde lectura.

### Área de seguridad

Alrededor del logo debe mantenerse un espacio libre equivalente, como mínimo, a la altura de la letra “B” del logotipo o al 15% del ancho del isotipo circular.

---

## 7. Estilo visual comercial

### Fondos recomendados

- Negro sólido.
- Gradientes oscuros con halos verdes/magenta.
- Texturas sutiles tipo humo, escenario, vidrio oscuro o luz ambiental.
- Fondos abstractos con baja saturación y acentos neón.

### Fondos a evitar

- Fondos blancos o muy claros para piezas principales.
- Fondos con demasiados colores compitiendo con el logo.
- Texturas saturadas que hagan perder lectura.
- Glow excesivo sobre todo el diseño.

### Estilo de glow

El glow debe acompañar la idea de neón, no tapar la forma.

Uso recomendado:

```css
.neon-green {
  color: #48E898;
  text-shadow:
    0 0 6px rgba(72, 232, 152, 0.65),
    0 0 18px rgba(72, 232, 152, 0.35);
}

.neon-pink {
  color: #E00078;
  text-shadow:
    0 0 6px rgba(224, 0, 120, 0.65),
    0 0 18px rgba(224, 0, 120, 0.35);
}
```

Para pantallas grandes puede subirse el glow. Para web, menú o PWA debe bajarse.

---

## 8. Tipografía comercial

### Recomendación principal

| Uso | Tipografía sugerida |
|---|---|
| Títulos grandes | Montserrat ExtraBold / Poppins Bold / Outfit Bold |
| Subtítulos | Montserrat SemiBold / Outfit Medium |
| Texto largo | Inter / Roboto / Lato |
| Piezas nocturnas especiales | Rajdhani / Orbitron / Audiowide, solo en títulos |

No se recomienda usar tipografías futuristas en textos largos. Funcionan bien para títulos, horarios, eventos o badges, pero cansan en lectura extendida.

---

## 9. Aplicaciones comerciales

### Web pública

- Header negro.
- Logo horizontal.
- Navegación en blanco/gris.
- Hover verde.
- Botón principal verde.
- Botón secundario con borde magenta.
- Fondos oscuros con halos suaves.

### Menú digital

- Fondo `#050505` o `#0B0F12`.
- Categorías con acento verde.
- Promos con acento magenta.
- Precios muy legibles en blanco.
- Evitar usar glow en todos los ítems.

### Señalética

- Isotipo circular para puntos de identificación.
- Verde para dirección/acción.
- Magenta para zonas de experiencia o eventos.
- Alto contraste y poco texto.

### Redes sociales

- Formatos 9:16 y 1:1.
- Uso fuerte de logo vertical o isotipo.
- Títulos grandes.
- Fondos oscuros.
- Un solo mensaje dominante por pieza.

### Pantallas y monitores

- Mayor tolerancia a glow y animaciones.
- Fondos oscuros animados.
- Logo neón con brillo controlado.
- Texto grande y poco contenido.

---

# PARTE B — SISTEMA EJECUTIVO / ANALÍTICO

## 10. Principio visual ejecutivo

El contexto ejecutivo debe ser BackStage, pero más sobrio. La prioridad es:

1. Lectura rápida.
2. Optimización de espacio.
3. Jerarquía visual clara.
4. Comparabilidad de datos.
5. Menos glow, más estructura.
6. Colores de marca usados como acentos, no como decoración permanente.

La estética ejecutiva recomendada es:

> Dark UI profesional + acentos BackStage + alta densidad de información + mínima distracción.

---

## 11. Paleta ejecutiva / dashboards

| Rol | Color | Hex |
|---|---:|---:|
| Fondo app | Base general | `#0B0F12` |
| Fondo panel | Secciones | `#111820` |
| Fondo card | Tarjetas / widgets | `#151B20` |
| Fondo tabla | Tabla principal | `#0F1419` |
| Fila alterna | Zebra sutil | `#131A21` |
| Borde | Separadores | `#263238` |
| Texto principal | Lectura | `#F2F2F2` |
| Texto secundario | Labels | `#9CA3AF` |
| Texto desactivado | Menor jerarquía | `#6B7280` |

## 12. Colores funcionales ejecutivos

| Estado / función | Color | Hex |
|---|---:|---:|
| Éxito / positivo / confirmado | Verde BackStage | `#48E898` |
| Destacado / promo / alerta comercial | Magenta BackStage | `#E00078` |
| Información neutral | Azul info | `#2DD4FF` |
| Advertencia | Ámbar | `#F59E0B` |
| Error / crítico | Rojo | `#EF4444` |
| Premium / VIP | Dorado suave | `#C9A646` |

### Regla importante

En dashboards no todo lo bueno debe ser verde ni todo lo malo debe ser rojo sin contexto. Conviene separar:

- **Color de marca:** identidad.
- **Color semántico:** significado operativo.

Ejemplo:

- Verde BackStage para botones activos y métricas positivas.
- Rojo solo para errores, pérdidas, diferencias críticas o alertas reales.
- Magenta para destacar promociones, eventos, top items o datos comerciales relevantes.

---

## 13. Uso del glow en dashboards

En dashboards, tablas y reportes el glow debe usarse muy poco.

### Permitido

- Logo pequeño en sidebar o header.
- Indicador activo.
- Estado seleccionado.
- Card principal de KPI, con brillo muy sutil.

### Evitar

- Glow en todas las tarjetas.
- Glow en tablas.
- Glow en texto pequeño.
- Glow en gráficos con muchos datos.
- Fondos animados detrás de información densa.

Regla práctica:

> Si el usuario está tomando decisiones con datos, el brillo debe bajar la voz.

---

## 14. Layout recomendado para dashboards

### Estructura general

- Sidebar izquierda compacta.
- Header superior con filtros globales.
- Zona principal con KPIs y gráficos.
- Tablas al final o en vistas dedicadas.

### Grid recomendado

Para desktop:

- 12 columnas.
- Margen exterior: 24 px.
- Gap entre cards: 16 px.
- Cards KPI: 3 o 4 por fila.
- Gráficos principales: 6 o 8 columnas.
- Tablas: ancho completo.

Para PWA / móvil:

- 1 columna.
- Cards compactas.
- Filtros colapsables.
- Tablas convertidas en cards o listas.
- Mostrar solo columnas críticas.

---

## 15. Cards KPI

### Estructura recomendada

Cada KPI debe tener:

1. Label corto.
2. Valor principal grande.
3. Variación o referencia.
4. Mini contexto.
5. Color semántico.

Ejemplo:

```text
VENTAS
Bs 12.450
+8.4% vs. semana anterior
Operativas cerradas: 4
```

### Tamaños recomendados

| Elemento | Desktop | Móvil |
|---|---:|---:|
| Label | 11–12 px | 11 px |
| Valor principal | 28–36 px | 24–30 px |
| Variación | 12–14 px | 12 px |
| Nota | 11–12 px | 11 px |

### Colores por KPI

- Ventas: blanco + acento verde.
- Margen: verde si es positivo.
- COGS: azul o blanco; no usar rojo salvo anomalía.
- Pour cost: verde/ámbar/rojo según umbrales.
- Diferencias de inventario: rojo o ámbar si requiere acción.

---

## 16. Tablas ejecutivas

Las tablas necesitan máxima claridad y densidad controlada.

### Recomendaciones

- Header fijo.
- Fila compacta: 36–44 px.
- Zebra sutil.
- Líneas divisorias suaves.
- Números alineados a la derecha.
- Texto alineado a la izquierda.
- Fechas centradas o alineadas a la izquierda según caso.
- No usar glow.
- Usar badges pequeños para estados.
- Congelar primeras columnas cuando haya muchas variables.

### Colores para tabla

| Elemento | Hex |
|---|---:|
| Header | `#111820` |
| Fila base | `#0F1419` |
| Fila alterna | `#131A21` |
| Hover | `#1B2630` |
| Borde | `#263238` |
| Texto | `#F2F2F2` |
| Texto secundario | `#9CA3AF` |

### Formato de números

- Moneda: `Bs 1.234,56`
- Porcentaje: `35,7%`
- Cantidades: máximo 2 decimales en vista ejecutiva.
- Costos unitarios: 4 a 6 decimales solo en vistas técnicas.
- Diferencias: siempre mostrar signo `+` o `-`.

---

## 17. Gráficos ejecutivos

### Principios

- Menos colores, más significado.
- No usar degradados innecesarios.
- No usar 3D.
- No saturar con etiquetas.
- Priorizar tooltips y filtros.
- Mostrar unidades claramente.

### Colores de series recomendados

| Serie | Color |
|---|---:|
| Serie principal | `#48E898` |
| Serie secundaria | `#E00078` |
| Serie neutral | `#2DD4FF` |
| Serie comparativa | `#C9A646` |
| Negativo / crítico | `#EF4444` |
| Advertencia | `#F59E0B` |

### Tipos de gráficos por uso

| Necesidad | Gráfico recomendado |
|---|---|
| Evolución de ventas | Línea o área suave |
| Comparar categorías | Barras horizontales |
| Ranking de productos | Barras horizontales ordenadas |
| Pour cost por producto | Barras + umbral |
| Distribución de ventas | Donut solo si son pocas categorías |
| Comparación real vs ideal | Barras agrupadas o bullet chart |
| Inventario físico vs sistema | Tabla + heatmap sutil |
| Margen por combo | Scatter o barras ordenadas |

### Recomendación específica para BackStage

Para rankings de productos, combos, pour cost y COGS, usar barras horizontales. Ahorran espacio, permiten nombres largos y son más legibles que tortas o gráficos circulares.

---

## 18. Infografías y reportes ejecutivos

Las infografías deben ser más limpias que las piezas comerciales.

### Reglas

- Fondo oscuro o blanco según destino.
- Máximo 2 colores de marca por página.
- Títulos claros.
- Números grandes.
- Iconos lineales simples.
- Usar divisores y bloques.
- Evitar saturación neón.

### Versión impresa

Para impresión ejecutiva se recomienda una versión clara:

| Rol | Hex |
|---|---:|
| Fondo | `#FFFFFF` |
| Texto principal | `#111827` |
| Texto secundario | `#4B5563` |
| Verde marca | `#1FBF78` |
| Magenta marca | `#C00068` |
| Gris borde | `#E5E7EB` |

En impresión, los neones originales pueden perder fidelidad. Conviene usar versiones ligeramente más sobrias.

---

## 19. Presentaciones ejecutivas

### Estructura recomendada

- Portada con logo neón sobre fondo negro.
- Slides interiores con fondo oscuro sobrio o fondo claro según audiencia.
- Una idea por slide.
- Gráficos grandes.
- Tablas solo cuando sean necesarias.
- Cierre con logo y contacto.

### Paleta para slides oscuros

- Fondo: `#0B0F12`
- Card: `#151B20`
- Texto: `#F2F2F2`
- Acento principal: `#48E898`
- Acento secundario: `#E00078`

### Paleta para slides claros

- Fondo: `#FFFFFF`
- Texto: `#111827`
- Gris: `#6B7280`
- Verde sobrio: `#1FBF78`
- Magenta sobrio: `#C00068`

---

## 20. Newsletter ejecutiva

Para newsletters internas o externas:

- Usar fondo claro si se enviará por email tradicional.
- Usar header negro con logo.
- KPIs en cards limpias.
- Gráficos simples.
- Evitar fondos con glow en el cuerpo del email.
- Usar verde para datos positivos y magenta para destacados comerciales.

---

# PARTE C — SISTEMA DIGITAL / PWA

## 21. PWA comercial

Para menú digital o app de cliente:

- Diseño más visual.
- Uso moderado de glow.
- Botones grandes.
- Fotografías o ilustraciones con fondo oscuro.
- Categorías claras.
- Promos visibles.
- Experiencia rápida.

## 22. PWA ejecutiva

Para dashboards, inventario, control operativo o administración:

- Diseño compacto.
- Sidebar colapsable.
- Filtros persistentes.
- Tablas optimizadas.
- Cards KPI compactas.
- Modo oscuro por defecto.
- Modo claro opcional para impresión/exportación.

---

## 23. Componentes recomendados

### Botón principal

- Fondo: `#48E898`
- Texto: `#050505`
- Radio: 999 px
- Peso: bold
- Hover: glow verde suave

### Botón secundario

- Fondo: transparente
- Borde: `#E00078`
- Texto: `#E00078`
- Hover: fondo magenta al 8–12%

### Card comercial

- Fondo: `#111111`
- Borde: verde/magenta al 20%
- Glow sutil en hover
- Imagen o icono protagonista

### Card ejecutiva

- Fondo: `#151B20`
- Borde: `#263238`
- Sin glow o glow mínimo
- Valor principal destacado

### Badge

| Estado | Fondo | Texto |
|---|---:|---:|
| Activo | `rgba(72,232,152,.12)` | `#48E898` |
| Promo | `rgba(224,0,120,.12)` | `#E00078` |
| Info | `rgba(45,212,255,.12)` | `#2DD4FF` |
| Alerta | `rgba(245,158,11,.12)` | `#F59E0B` |
| Crítico | `rgba(239,68,68,.12)` | `#EF4444` |

---

## 24. Código base CSS recomendado

```css
:root {
  --bs-bg: #050505;
  --bs-bg-app: #0B0F12;
  --bs-card: #151B20;
  --bs-card-dark: #111111;
  --bs-border: #263238;

  --bs-green: #48E898;
  --bs-pink: #E00078;
  --bs-blue: #2DD4FF;
  --bs-purple: #7A00FF;
  --bs-gold: #C9A646;

  --bs-success: #48E898;
  --bs-info: #2DD4FF;
  --bs-warning: #F59E0B;
  --bs-danger: #EF4444;

  --bs-text: #F2F2F2;
  --bs-muted: #9CA3AF;
  --bs-disabled: #6B7280;

  --bs-radius-card: 16px;
  --bs-radius-panel: 24px;
}
```

---

## 25. Reglas rápidas de decisión

### Si es comercial

- Puede brillar.
- Puede emocionar.
- Puede usar fondos abstractos.
- Puede usar más magenta.
- Puede usar animación.
- Debe tener alto impacto visual.

### Si es ejecutivo

- Debe leerse rápido.
- Debe ahorrar espacio.
- Debe reducir glow.
- Debe usar grillas.
- Debe priorizar contraste y jerarquía.
- Debe usar colores por significado, no solo por estética.

---

## 26. Errores a evitar

- Usar verde y magenta al 50/50 en todas las piezas.
- Poner glow en textos pequeños.
- Usar fondos claros sin adaptar el logo.
- Usar demasiadas tipografías.
- Usar gráficos 3D.
- Usar demasiados colores en dashboards.
- Convertir una tabla ejecutiva en una pieza promocional.
- Usar screenshots borrosos o fondos saturados detrás de datos.
- Exportar reportes impresos con colores neón sin revisar cómo salen en papel.

---

## 27. Recomendación final

BackStage debe manejar una identidad dual:

1. **BackStage Comercial:** neón, noche, música, experiencia, emoción.
2. **BackStage Ejecutivo:** oscuro, sobrio, analítico, eficiente, preciso.

La marca se mantiene unificada porque ambos sistemas comparten los mismos colores, tipografías base y lenguaje visual. Lo que cambia es la intensidad.

La regla maestra:

> En piezas comerciales, el neón vende la experiencia. En piezas ejecutivas, el neón organiza la información.

<!-- Tip: Use /create-skill in chat to generate content with agent assistance -->

