---
name: Electric Industrial
colors:
  surface: '#0d1515'
  surface-dim: '#0d1515'
  surface-bright: '#333b3b'
  surface-container-lowest: '#080f10'
  surface-container-low: '#151d1e'
  surface-container: '#192122'
  surface-container-high: '#232b2c'
  surface-container-highest: '#2e3637'
  on-surface: '#dce4e5'
  on-surface-variant: '#b9cacb'
  inverse-surface: '#dce4e5'
  inverse-on-surface: '#2a3233'
  outline: '#849495'
  outline-variant: '#3b494b'
  surface-tint: '#00dbe9'
  primary: '#dbfcff'
  on-primary: '#00363a'
  primary-container: '#00f0ff'
  on-primary-container: '#006970'
  inverse-primary: '#006970'
  secondary: '#bcc7de'
  on-secondary: '#263143'
  secondary-container: '#3e495d'
  on-secondary-container: '#aeb9d0'
  tertiary: '#fff5de'
  on-tertiary: '#3b2f00'
  tertiary-container: '#fed639'
  on-tertiary-container: '#715d00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#7df4ff'
  primary-fixed-dim: '#00dbe9'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#004f54'
  secondary-fixed: '#d8e3fb'
  secondary-fixed-dim: '#bcc7de'
  on-secondary-fixed: '#111c2d'
  on-secondary-fixed-variant: '#3c475a'
  tertiary-fixed: '#ffe179'
  tertiary-fixed-dim: '#eac324'
  on-tertiary-fixed: '#231b00'
  on-tertiary-fixed-variant: '#554500'
  background: '#0d1515'
  on-background: '#dce4e5'
  surface-variant: '#2e3637'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  body-base:
    fontFamily: Space Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0em
  label-mono:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.0'
    letterSpacing: 0.05em
  data-tabular:
    fontFamily: Space Grotesk
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.4'
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  container-max: 1440px
  gutter: 16px
---

## Brand & Style
This design system targets high-performance technical environments, developer tools, and logistics interfaces. It evokes a sense of "digital precision" and "industrial resilience." The aesthetic is a fusion of **Industrial Minimalism** and **Cybernetic Accents**, focusing on utility, speed, and clarity. 

The emotional response should be one of focused control—reminiscent of a command center or a high-end server rack. The interface prioritizes data density without sacrificing legibility, using light and color only where attention is required. The style relies on sharp geometry, monochromatic surfaces, and high-frequency "electric" highlights to guide the user through complex information hierarchies.

## Colors
The palette is rooted in a deep, obsidian-like dark mode. 

- **Primary (Electric Cyan):** Used exclusively for high-priority interactive elements, status indicators, and critical data points. It is often accompanied by an outer glow or "bloom" effect to simulate a neon light source.
- **Secondary (Deep Blue):** Utilized for structural containment, borders, and subtle background elevations. It provides a cooling contrast to the intensity of the cyan.
- **Surface (#131314):** The foundational ground. All other colors must maintain high contrast ratios against this base.
- **Functional Colors:** Success is handled by a desaturated teal, while errors use a sharp, high-chroma red to maintain the industrial warning aesthetic.

## Typography
This design system utilizes **Space Grotesk** exclusively to maintain a technical, geometric consistency. 

- **Headlines:** Use Bold or SemiBold weights. Tighten letter spacing on larger displays to create a more "engineered" look.
- **Body:** Standard weight for readability. Space Grotesk's open apertures ensure legibility on dark backgrounds.
- **Labels:** Use the "label-mono" style for metadata, ID tags, and secondary navigation. The uppercase treatment and slight tracking increase the industrial feel.
- **Data Points:** When displaying numerical inventories or timestamps, use tabular figures to ensure columns align perfectly in dense lists.

## Layout & Spacing
The layout follows a strict **12-column grid** with a 4px base unit. 

- **Grid:** Use a fluid grid for internal dashboards, but cap the maximum width at 1440px for content-heavy views.
- **Rhythm:** Vertical rhythm should be disciplined, using 16px (md) as the default padding for containers and 8px (sm) for internal element grouping.
- **Industrial Density:** Components should feel tightly packed but organized. Use "Heavy" margins (40px+) only to separate major functional modules.

## Elevation & Depth
Depth is not communicated through shadows, but through **Tonal Layering** and **Luminous Outlines**.

- **Level 0 (Base):** #131314.
- **Level 1 (Surface):** #1C1C1E. Used for cards and secondary panels.
- **Level 2 (Active):** #2C2C2E. Used for hovered or active states.
- **Containment:** Instead of drop shadows, use 1px solid borders in Deep Blue (#1E293B). 
- **Luminosity:** High-priority elements use a "Cyan Glow"—a 1px Cyan border accompanied by a soft 4px to 8px Cyan outer blur (box-shadow) at low opacity (20-30%).

## Shapes
This design system employs a **Sharp (0px)** corner radius for all primary structural elements (Cards, Buttons, Inputs, Panels). This reinforces the industrial, machined aesthetic. 

Subtle deviations are allowed only for circular status pips or specific icon containers where geometric differentiation is required for instant recognition. All containment lines should be 1px or 2px, never thicker, to maintain a "blueprint" precision.

## Components
- **Buttons:** Primary buttons feature a solid Electric Cyan background with black text. Secondary buttons are ghost-style with a Deep Blue border that transitions to Cyan on hover.
- **Inputs:** Dark surfaces with a 1px Deep Blue bottom border. Upon focus, the border turns Electric Cyan with a subtle horizontal "pulse" glow.
- **Chips/Tags:** Used for status. They should feature a low-opacity Cyan background with a solid Cyan left-hand "indicator" border (2px).
- **Data Tables:** High-density rows with 1px Deep Blue separators. Hover states should trigger a full-row Cyan hairline border.
- **Inventory Cards:** Sharp-edged containers with a top-aligned label in uppercase. Include a "Signal" corner—a small Cyan triangle or square in the top right to indicate active status.
- **Progress Bars:** Thin 4px tracks in Deep Blue, with an Electric Cyan fill that has a subtle "inner glow" to look like a glass tube filled with light.