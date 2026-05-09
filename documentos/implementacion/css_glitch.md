El efecto **glitch** está construido sobre unos pocos parámetros principales y varias piezas CSS internas. Te los describo de forma ordenada:

---

# 1) Parámetros principales del glitch

Estos son los valores que controlan el efecto desde las variables CSS:

```css
--glitch-offset: 6px;
--glitch-opacity: 0.55;
--glitch-speed: 1.4s;
```

## `--glitch-offset`

**Valor por defecto:** `6px`

Controla **cuánto se desplazan lateral o ligeramente verticalmente** las capas del glitch.

### Qué hace visualmente

* Si el valor es pequeño, el glitch se ve **sutil**
* Si el valor es grande, el glitch se ve **más agresivo y roto**

### Ejemplo

* `2px` → pequeño corrimiento
* `6px` → glitch moderado
* `12px` o más → efecto mucho más evidente

---

## `--glitch-opacity`

**Valor por defecto:** `0.55`

Controla la **opacidad de las capas glitch**.

### Qué hace visualmente

* Valores bajos → el glitch apenas se percibe
* Valores altos → las capas desalineadas se ven mucho más

### Ejemplo

* `0.20` → muy tenue
* `0.55` → equilibrado
* `0.90` → muy fuerte

---

## `--glitch-speed`

**Valor por defecto:** `1.4s`

Controla la **duración del ciclo completo** de las animaciones de glitch.

### Qué hace visualmente

* valores más bajos = glitch más rápido
* valores más altos = glitch más lento

### Ejemplo

* `0.6s` → nervioso, intenso
* `1.4s` → balanceado
* `2.5s` → más pausado

---

# 2) Parámetro de activación

## `glitchToggle`

Es el checkbox que activa o desactiva el glitch.

Internamente agrega o quita esta clase del `<body>`:

```css
body.glitch-on
```

Cuando esa clase está activa:

* aparecen las capas glitch
* aparecen también las scanlines

Cuando no está activa:

* el logo queda solo con glow fijo
* el glitch desaparece

---

# 3) Cómo está armado el glitch internamente

El efecto no se hace sobre una sola imagen, sino sobre **varias copias de la misma imagen superpuestas**.

### Capas usadas

1. **`logo-main`**
   La capa principal del logo

   * tiene el glow fijo
   * no se anima

2. **`glitch-red`**
   Una copia del logo teñida hacia magenta/rojo

3. **`glitch-cyan`**
   Otra copia del logo teñida hacia cian/verde

4. **`scanlines`**
   Una capa superior con líneas horizontales tipo pantalla

---

# 4) Clases internas del glitch

## `.glitch-layer`

Es la base de las capas glitch:

```css
.glitch-layer {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  opacity: 0;
  will-change: transform, opacity, clip-path, filter;
  transition: opacity 180ms ease;
}
```

### Qué significa

* `position: absolute; inset: 0;`
  Hace que la capa quede exactamente encima del logo original

* `opacity: 0;`
  Por defecto está oculta

* `will-change`
  Le avisa al navegador que esa capa va a animarse

* `transition: opacity 180ms ease;`
  Hace más suave el encendido/apagado del glitch

Y cuando el glitch está activo:

```css
body.glitch-on .glitch-layer {
  opacity: var(--glitch-opacity);
}
```

---

## `.glitch-red`

```css
.glitch-red {
  filter:
    sepia(1) saturate(8) hue-rotate(300deg) brightness(1.15)
    drop-shadow(0 0 8px rgba(255,0,140,0.7));
  mix-blend-mode: screen;
  animation: glitchRed var(--glitch-speed) steps(2, end) infinite;
}
```

### Qué hace

* recolorea la capa hacia tonos rosados/magenta
* le agrega una pequeña aura
* la anima con `glitchRed`

### Cosas importantes

#### `mix-blend-mode: screen`

Hace que la capa se mezcle luminosamente con la de abajo.
Eso ayuda a que el glitch se vea “electrónico” en vez de parecer una simple copia.

#### `steps(2, end)`

Hace que la animación tenga saltos bruscos en vez de movimiento fluido.
Eso es clave para que se vea como glitch y no como deslizamiento normal.

---

## `.glitch-cyan`

```css
.glitch-cyan {
  filter:
    sepia(1) saturate(8) hue-rotate(120deg) brightness(1.2)
    drop-shadow(0 0 8px rgba(53,242,170,0.7));
  mix-blend-mode: screen;
  animation: glitchCyan calc(var(--glitch-speed) * 0.92) steps(2, end) infinite reverse;
}
```

### Qué hace

* recolorea la copia hacia tonos cian/verde
* la anima con un tiempo ligeramente diferente
* usa `reverse` para que no se comporte exactamente igual que la roja

### Por qué eso ayuda

Si ambas capas se movieran igual, el glitch se vería pobre.
Al hacerlas diferentes:

* una se adelanta
* otra se atrasa
* el efecto se vuelve más vivo

---

# 5) Las animaciones reales del glitch

---

## `@keyframes glitchRed`

Esta animación:

* mueve la capa roja
* recorta franjas horizontales con `clip-path`
* vuelve luego a estado normal

Ejemplo de un tramo:

```css
10%  { transform: translate(calc(var(--glitch-offset) * -1), 1px); clip-path: inset(5% 0 78% 0); }
12%  { transform: translate(calc(var(--glitch-offset) * 0.6), -1px); clip-path: inset(20% 0 58% 0); }
14%  { transform: translate(calc(var(--glitch-offset) * -0.4), 0px); clip-path: inset(40% 0 38% 0); }
```

### Qué significa

* `transform: translate(...)`
  desplaza la copia del logo

* `clip-path: inset(...)`
  muestra solo una franja horizontal del logo
  Eso genera el típico efecto de “partes del logo saltando”

---

## `@keyframes glitchCyan`

Hace lo mismo, pero con otros tiempos y otros recortes.

Eso produce el efecto de:

* **doble desalineación cromática**
* cortes en diferentes partes del logo
* sensación digital más convincente

---

# 6) Scanlines

## `.scanlines`

```css
.scanlines {
  position: absolute;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  opacity: 0;
  transition: opacity 180ms ease;
  background:
    repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.00) 0px,
      rgba(255,255,255,0.00) 3px,
      rgba(255,255,255,0.06) 4px
    );
  mix-blend-mode: overlay;
  animation: scanMove 7s linear infinite;
}
```

### Qué hace

Agrega líneas finas horizontales tipo:

* CRT
* monitor viejo
* interferencia de pantalla

### Parámetros implícitos

* cada línea aparece cada `4px`
* opacidad base muy baja
* movimiento lento con `scanMove 7s`

Cuando el glitch está activo:

```css
body.glitch-on .scanlines {
  opacity: 0.28;
}
```

Eso hace que las líneas solo aparezcan cuando activas el modo glitch.

---

# 7) Resumen rápido de cada control que ve el usuario

## Controles de glitch visibles en la interfaz

### **Activar efecto glitch**

Enciende o apaga:

* capas duplicadas de color
* cortes por franjas
* scanlines

### **Desplazamiento Glitch**

Controla cuánto se separan las copias del logo.

### **Opacidad Glitch**

Controla qué tan visibles son las capas glitch.

### **Velocidad Glitch**

Controla la rapidez del ciclo de animación.

---

# 8) En una frase: ¿cómo funciona el glitch?

El efecto glitch se logra así:

* se toma el logo original
* se crean **dos copias coloreadas**
* esas copias se **desplazan en saltos**
* se muestran solo en **franjas horizontales** con `clip-path`
* se mezclan con `screen`
* encima se agregan **scanlines**
* todo eso se activa con `body.glitch-on`

---

# 9) Si quieres tunearlo, estas son buenas guías

## Glitch más sutil

```css
--glitch-offset: 3px;
--glitch-opacity: 0.25;
--glitch-speed: 2s;
```

## Glitch equilibrado

```css
--glitch-offset: 6px;
--glitch-opacity: 0.55;
--glitch-speed: 1.4s;
```

## Glitch agresivo / cyberpunk

```css
--glitch-offset: 12px;
--glitch-opacity: 0.85;
--glitch-speed: 0.8s;
```

---