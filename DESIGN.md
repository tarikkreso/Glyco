# Glyco Frosted Glass Design Language

This is the current visual target for Glyco. The whole app should gradually move toward a glossy, frosted, calm medical style with a light milky glass tone.

## Core Feeling

Glyco should feel calm, intelligent, clinical, alive, and premium. The interface should avoid cartoon styling, hard red alarm states, heavy cards, and generic dashboard density. Health risk should feel noticeable but not frightening.

The visual metaphor is a light clinical glass environment with translucent panels, soft biological signal rings, and a central living agent form. Dark green can appear as depth behind Glyco or in focused chat elements, but it should not dominate the whole app.

## Color System

Use pale green-white glass as the primary app background:

- Base: `#f6faf5`
- Soft wash: `#dde9df`
- Deep accent surface: `rgba(18, 32, 24, .78)` for focused chat or central depth only
- Frosted card: `rgba(255, 255, 255, .62)`
- Frosted field: `rgba(247, 252, 245, .74)`
- Subtle border: `rgba(222, 243, 226, .62)`
- Primary text: `#154539`
- Muted text: `#52635a`
- Primary green: `#154539`

State colors should be soft and medical:

- Stable glucose: soft green glow, slow breathing animation.
- Slightly elevated: brighter yellow-green center, quicker but still gentle pulse.
- High glucose or high weekly risk: warm amber outer ring, never aggressive red.
- Low glucose or low-energy symptoms: cooler pale green/blue tint, smaller dimmer core.
- No data: neutral gray-green, minimal glow.
- Good day: larger bright green center, smoother animation.
- Risk detected: more visible outer contour ring with gentle pulse.

## Frosted Glass Panels

Panels should use translucent backgrounds and visible but quiet borders:

```css
background:
  radial-gradient(circle at 26% 0%, rgba(210, 255, 189, .3), transparent 38%),
  rgba(255, 255, 255, .62);
border: 1px solid rgba(222, 243, 226, .62);
box-shadow: 0 26px 70px rgba(31, 54, 39, .18), inset 0 1px 0 rgba(255,255,255,.78);
backdrop-filter: blur(22px);
border-radius: 16px to 24px;
```

Use glass panels for modals, side panels, chat windows, insight blocks, and major controls. Avoid nesting glass cards inside other cards unless the inner item is a distinct repeated object.

## Glyco Avatar

Glyco is the app's central agent presence. It should be an abstract, glassmorphic, organic rhomboid:

- Soft rounded diamond / rhomboid silhouette.
- Slightly irregular contour edges.
- Multiple semi-transparent contour layers.
- Frosted translucent body.
- Soft glowing center.
- No face, eyes, mouth, robot features, mascot traits, or cartoon styling.

The current implementation uses clipped rhomboid contour layers and CSS variables for state-driven color changes. Keep this pattern and refine it rather than replacing it with a static image.

Interaction:

- Hover increases glow subtly.
- Click emits a contour ripple/signal pulse.
- Risk states should affect the outer ring more than the center.

## Layout

The main screen should prioritize Glyco at the center, with clinical metrics orbiting around it. Keep the interface spacious and focused:

- Light frosted green-white background, with darker green only where depth or contrast is needed.
- Central Glyco avatar.
- Floating frosted metric chips.
- Bottom chat dock, centered in the available content area.
- Secondary data below the fold or in compact frosted panels.

Other app pages should adopt the same shell:

- Frosted sidebar and topbar.
- Collapsible left navigation.
- Glass modals and forms.
- Light green-white frosted sections depending on page density, with deep green reserved for accents and high-contrast chat bubbles.

## Chat

Chat starts as a centered bottom dock and should stay small while the user types or sends messages from the main screen. It must not auto-expand.

Expansion is explicit:

- The small chat has an expand button.
- Clicking expand should animate/scroll the chat outward and open the separate Agent chat screen.
- The Agent screen should use a light frosted AI workspace style, not a dark fullscreen overlay.
- Keep the chat compose field visible at the bottom of the Agent chat.
- Avoid covering critical controls in dock mode.

## Forms

Forms should avoid flat white clinical boxes. Use frosted field groups:

- Each label/input group may sit on a translucent white surface.
- Inputs should be slightly translucent with soft borders.
- Primary submit buttons can keep the deep Glyco green with glassy shadow.
- Help popovers should also use frosted backgrounds.

## Motion

Motion should feel biological and calm:

- Slow breathing for stable states.
- Slightly faster pulse for elevated states.
- Gentle ripple on click.
- Modals scale and fade from the point of interaction.
- Respect `prefers-reduced-motion`.

Avoid bouncy, cartoon, abrupt, or aggressive animation.

## Implementation Notes

Prefer shared CSS tokens and reusable classes before restyling each page independently. The current source of truth is:

- Main screen: `frontend/src/pages/Overview.tsx`
- Visual system styles: `frontend/src/styles.css`
- Global log modal: `frontend/src/components/GlobalLogNewData.tsx`
- Data log form: `frontend/src/components/LogNewDataForm.tsx`
- Shell/sidebar: `frontend/src/components/Layout.tsx`

When redesigning remaining pages, keep behavior intact first, then convert surfaces to the frost system.

---

# Legacy Clinical Editorial System

The earlier app design used a flatter clinical editorial system. Keep this section as a useful baseline for typography, density, and medical restraint while the app transitions to the frosted glass language.

## Legacy Colors

- `surface`: `#f9faf7`
- `surface-low`: `#f3f4f1`
- `surface-card`: `#ffffff`
- `text`: `#1a1c1b`
- `muted`: `#404945`
- `outline`: `#c0c8c4`
- `primary`: `#154539`
- `primary-soft`: `#d1e8da`
- `accent`: `#2f5d50`
- `error`: `#ba1a1a`
- `error-bg`: `#ffdad6`
- `rust`: `#784840`

## Legacy Typography

Use Manrope for headings and Inter for body, data labels, controls, and dense dashboard content.

- Display: Manrope, 30px, 700, 38px line height.
- Headline: Manrope, 20-24px, 600.
- Body: Inter, 14-16px, 400.
- Label: Inter, 11-12px, 700-800, uppercase, tracked.

## Legacy Layout Principles

The old system favored dense, structured information with lean spacing, thin borders, and predictable clinical dashboards. This remains useful for pages like Reports, Monitoring, and Risk Check, but the surface treatment should move from flat paper cards toward frosted translucent panels.

## Legacy Component Rules

- Cards: white background, 12px radius, 1px border.
- Buttons: primary deep green, secondary white with border.
- Inputs: white background, 1px border, 2px teal focus outline.
- Data chips: small rounded tags with muted background.
- Clinical indicators: use calm warning/danger colors, avoiding aggressive red except for true error states.
