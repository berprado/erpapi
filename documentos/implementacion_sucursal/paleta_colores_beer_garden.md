# Paleta de colores recomendada — Beer Garden

## 1. Objetivo

Esta paleta de colores toma como referencia directa la identidad visual de los logos de **Beer Garden**.

La combinación principal se apoya en cuatro ideas visuales:

- **Negro profundo** para transmitir ambiente nocturno, elegancia y contraste.
- **Carbón** para aportar profundidad sin depender exclusivamente del negro.
- **Dorado cálido** como color distintivo de marca.
- **Blanco cálido / marfil** para conservar excelente legibilidad y reforzar el carácter premium.

El objetivo para la landing page es mantener una estética de **cervecería premium, artesanal y nocturna**, evitando que el dorado domine excesivamente la interfaz.

---

## 2. Paleta principal

| Rol | Nombre | HEX | Uso recomendado |
|---|---|---|---|
| Fondo principal | Negro Beer Garden | `#050505` | Hero, fondo general, footer y secciones oscuras |
| Fondo secundario | Carbón | `#2F3030` | Tarjetas, bloques de contenido y secciones alternas |
| Color de marca | Dorado principal | `#C5A674` | Botones, iconos, bordes, destacados y elementos de marca |
| Dorado secundario | Dorado oscuro / bronce suave | `#8C7755` | Hover, estados secundarios, sombras y detalles |
| Texto principal | Marfil | `#FEFEFD` | Títulos y textos de máxima jerarquía |
| Texto secundario | Champagne | `#E5E1D7` | Párrafos y textos secundarios sobre fondos oscuros |
| Detalles | Taupe | `#655C49` | Divisores, líneas, bordes discretos y elementos secundarios |

---

## 3. Colores principales de identidad

La combinación visual central debería ser:

- **Negro:** `#050505`
- **Carbón:** `#2F3030`
- **Dorado:** `#C5A674`
- **Marfil:** `#FEFEFD`

Estos cuatro colores deberían dominar aproximadamente el **90 % de la interfaz**.

---

## 4. Proporción recomendada de uso

Para evitar una landing excesivamente cargada y mantener un aspecto premium:

- **60 % — Negro `#050505`**
- **20 % — Carbón `#2F3030`**
- **10 % — Blanco / Marfil `#FEFEFD`**
- **7 % — Dorado `#C5A674`**
- **3 % — Tonos auxiliares**

El dorado debe funcionar principalmente como **acento visual**, no como color de fondo dominante.

---

## 5. Color complementario opcional

Para reforzar de manera sutil el concepto de **Garden**, se recomienda incorporar un verde oliva oscuro como color auxiliar:

| Rol | Nombre | HEX | Uso recomendado |
|---|---|---|---|
| Color complementario | Verde oliva oscuro | `#596044` | Detalles botánicos, iconos decorativos, etiquetas y elementos secundarios |

### Regla de uso

El verde oliva:

- No debería competir con el dorado.
- No debería utilizarse como color principal de los botones.
- Debe aparecer de forma discreta.
- Puede utilizarse en ilustraciones, plantas, hojas, patrones, iconografía o detalles vinculados al concepto de jardín.

Paleta extendida:

- `#050505` — Negro
- `#2F3030` — Carbón
- `#C5A674` — Dorado
- `#FEFEFD` — Marfil
- `#596044` — Verde oliva

---

## 6. Aplicación recomendada en la landing page

### Hero

- Fondo: `#050505`
- Logo: versión original
- Título: `#FEFEFD`
- Texto secundario: `#E5E1D7`
- CTA principal: `#C5A674`
- CTA secundario: transparente con borde `#C5A674`

### Secciones de contenido

Alternar principalmente entre:

- `#050505`
- `#2F3030`

Esto permite generar profundidad sin perder coherencia visual.

### Tarjetas

Fondo recomendado:

- `#2F3030`
- Variante elevada: `#353636`

Bordes:

- `#655C49`
- Dorado `#C5A674` solamente para destacar tarjetas importantes

### Tipografía

- Títulos principales: `#FEFEFD`
- Texto normal: `#E5E1D7`
- Texto de menor jerarquía: `#B4B0A2`
- Enlaces y destacados: `#C5A674`

---

## 7. Variables CSS recomendadas

```css
:root {
    /* Backgrounds */
    --bg-primary: #050505;
    --bg-secondary: #2F3030;
    --bg-elevated: #353636;

    /* Brand */
    --brand-gold: #C5A674;
    --brand-gold-dark: #8C7755;

    /* Complementary */
    --brand-olive: #596044;

    /* Typography */
    --text-primary: #FEFEFD;
    --text-secondary: #E5E1D7;
    --text-muted: #B4B0A2;

    /* Details */
    --border-gold: #C5A674;
    --border-subtle: #655C49;

    /* Interaction */
    --button-primary: #C5A674;
    --button-primary-hover: #8C7755;
}
```

---

## 8. Botón principal

```css
.btn-primary {
    background: #C5A674;
    color: #050505;
    border: 1px solid #C5A674;
}

.btn-primary:hover {
    background: #8C7755;
    border-color: #8C7755;
}
```

---

## 9. Botón secundario

```css
.btn-secondary {
    background: transparent;
    color: #FEFEFD;
    border: 1px solid #C5A674;
}

.btn-secondary:hover {
    background: #C5A674;
    color: #050505;
}
```

---

## 10. Consideraciones de diseño

El dorado `#C5A674` tiene un carácter más cálido y orgánico que un dorado metálico tradicional.

Visualmente puede asociarse con:

- Malta
- Cerveza artesanal
- Madera clara
- Latón envejecido
- Ambiente cálido
- Experiencias gastronómicas premium

Por esta razón se recomienda evitar dorados excesivamente brillantes o amarillos, ya que podrían alejar la identidad visual de Beer Garden hacia una estética demasiado lujosa o corporativa.

---

## 11. Dirección visual recomendada

La landing debería transmitir principalmente:

**Cervecería premium + jardín nocturno + gastronomía artesanal + ambiente social.**

Palabras clave para mantener coherencia en futuras decisiones de diseño:

- Oscuro
- Cálido
- Artesanal
- Premium
- Nocturno
- Natural
- Acogedor
- Cervecero
- Elegante
- Orgánico

---

## 12. Paleta resumida

```text
NEGRO PRINCIPAL     #050505
CARBÓN              #2F3030
DORADO PRINCIPAL    #C5A674
DORADO OSCURO       #8C7755
MARFIL              #FEFEFD
CHAMPAGNE           #E5E1D7
TAUPE               #655C49
VERDE OLIVA         #596044
```

---

**Identidad visual propuesta para Beer Garden**  
Base para diseño de landing page y sistema visual digital.
