---
name: Clinical Editorial System
colors:
  surface: '#f9faf7'
  surface-dim: '#d9dad8'
  surface-bright: '#f9faf7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f1'
  surface-container: '#edeeec'
  surface-container-high: '#e7e8e6'
  surface-container-highest: '#e2e3e0'
  on-surface: '#1a1c1b'
  on-surface-variant: '#404945'
  inverse-surface: '#2e3130'
  inverse-on-surface: '#f0f1ee'
  outline: '#717975'
  outline-variant: '#c0c8c4'
  surface-tint: '#396759'
  primary: '#154539'
  on-primary: '#ffffff'
  primary-container: '#2f5d50'
  on-primary-container: '#a3d4c3'
  inverse-primary: '#a0d1c0'
  secondary: '#4e6358'
  on-secondary: '#ffffff'
  secondary-container: '#d1e8da'
  on-secondary-container: '#54695e'
  tertiary: '#5d322a'
  on-tertiary: '#ffffff'
  tertiary-container: '#784840'
  on-tertiary-container: '#fbbaaf'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#bceddc'
  primary-fixed-dim: '#a0d1c0'
  on-primary-fixed: '#002019'
  on-primary-fixed-variant: '#204f42'
  secondary-fixed: '#d1e8da'
  secondary-fixed-dim: '#b5ccbf'
  on-secondary-fixed: '#0c1f17'
  on-secondary-fixed-variant: '#374b41'
  tertiary-fixed: '#ffdad4'
  tertiary-fixed-dim: '#f7b7ac'
  on-tertiary-fixed: '#33110b'
  on-tertiary-fixed-variant: '#683a33'
  background: '#f9faf7'
  on-background: '#1a1c1b'
  surface-variant: '#e2e3e0'
typography:
  display-sm:
    fontFamily: Manrope
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Manrope
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 12px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system establishes a high-precision clinical environment filtered through the lens of a premium editorial publication. The aesthetic is rooted in **Minimalism** and **Modern Corporate** styles, prioritizing legibility and a sense of calm authority. By stripping away digital trends like glassmorphism and gradients, the UI achieves a "paper-like" permanence that feels medically trustworthy and serious. 

The focus is on dense, structured information presented with rhythmic clarity. It avoids visual noise, using structural lines and thoughtful white space to guide the clinician’s eye through complex datasets without fatigue.

## Colors

The palette is anchored by a warm, off-white background (#F6F4EF) that reduces eye strain compared to pure white, evoking the feel of high-quality medical stationery. 

- **Primary Accent:** A deep teal (#2F5D50) used for critical actions and primary navigation, conveying stability and professional depth.
- **Secondary Accents:** Muted sage (#60756A) and slate (#5E7482) are utilized for categorizing data without creating visual competition.
- **Functional Colors:** Warning and Danger tones are desaturated and earthy. They remain highly visible against the parchment background but avoid the "alarmist" vibration of neon signals, maintaining a calm atmosphere even during critical alerts.
- **Borders:** A specific parchment-tone border (#DDD7CE) is the primary tool for element separation.

## Typography

This system employs a dual-font strategy to balance editorial sophistication with functional utility. 

**Manrope** is used for headlines and section titles. Its geometric yet humanist qualities provide a modern, approachable authority. **Inter** is used for all body copy, data points, and labels; its high x-height and exceptional legibility at small sizes make it ideal for dense clinical dashboards. 

Information density is managed through strict hierarchical scaling. Labels use an uppercase, tracked-out style to differentiate metadata from primary patient values.

## Layout & Spacing

The layout utilizes a **fluid grid** optimized for mobile-first clinical workflows. A 4px baseline grid ensures vertical rhythm across dense data tables and patient charts. 

On mobile devices, margins are kept tight (16px) to maximize screen real estate for charts and vitals. Component internal padding is lean (12px) to allow for higher information density. The layout philosophy relies on "Zonal Grouping"—using thin borders and consistent spacing to define logical clusters of information rather than expansive white space.

## Elevation & Depth

This system intentionally rejects shadows and blurs to maintain a "flat editorial" aesthetic. Depth is achieved through **Tonal Layering** and **Bold Outlines**.

- **Level 0 (Background):** The base parchment (#F6F4EF).
- **Level 1 (Cards/Surface):** Pure white (#FFFFFF) surfaces used for content modules.
- **Definition:** All depth is communicated via 1px solid borders (#DDD7CE). When an element needs to feel "raised" or active, the border weight remains the same but the color may shift to the primary accent or a slightly darker neutral. 
- **Interactive States:** Hover or active states are indicated by subtle background color shifts (e.g., from White to a very pale Tint of Teal) rather than shadow-based lifts.

## Shapes

The shape language is disciplined and consistent. A standard **12px (0.75rem)** radius is applied to all cards, buttons, and input fields. This moderate rounding softens the clinical precision just enough to feel "premium" and modern without veering into "playful."

All containers must utilize the defined 1px border. Interactive components like checkboxes and radio buttons follow the same 1px stroke weight to ensure a cohesive, technical drawing feel across the interface.

## Components

- **Cards:** White background, 12px radius, 1px #DDD7CE border. No shadow. Header sections within cards should be separated by a horizontal 1px line.
- **Buttons:** Primary buttons use a solid Teal (#2F5D50) fill with white text. Secondary buttons use a transparent background with a 1px border.
- **Inputs:** Fields use a white background and 1px border. Focus states are indicated by a 2px Teal border, never a glow or shadow.
- **Data Chips:** Small, 12px radius tags with a light sage background (#60756A at 10% opacity) and dark text for categorizing patient status.
- **Information Density:** For data-heavy views, use "Condensed Lists" where row height is minimized and separators are subtle 1px lines, ensuring maximum visibility of laboratory results or medication history.
- **Clinical Indicators:** Use small, solid geometric shapes (circles/triangles) in Warning or Danger colors for status alerts, paired with bolded Inter text.