# GitHub Design System Analysis

> Source: https://github.com/  
> Measured: May 17, 2026  
> Analysis by DesignMD

---

---
name: GitHub
url: https://github.com/
colors:
  primary: '#5fed83'
  primary-dark: '#08872b'
  background: '#0d1117'
  surface: '#1f2328'
  surface-light: '#f0f6fc'
  text-primary: '#f0f6fc'
  text-primary-on-light: '#1f2328'
  text-muted: '#9198a1'
  text-accent: '#8dd6ff'
  border: '#484f58'
typography:
  display:
    family: Mona Sans
    size: 64px
    weight: 600
    line-height: 1.1
  heading:
    family: Mona Sans
    size: 48px
    weight: 600
    line-height: 1.2
  body:
    family: Mona Sans
    size: 16px
    weight: 400
    line-height: 1.5
  code:
    family: ui-monospace
    size: 14px
    weight: 400
    line-height: 1.5
spacing:
  base: 4px
  scale: [4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
radius:
  sm: 6px
  md: 8px
  lg: 16px
  full: 9999px
elevation:
  glow: '0 0 24px rgba(141, 214, 255, 0.15)'
  glow-hover: '0 0 32px rgba(141, 214, 255, 0.25)'
components:
  button-primary:
    bg: '{colors.primary}'
    text: '#000000'
    radius: '{radius.sm}'
    padding: '11px 23px'
    border: '1px solid {colors.primary}'
  card:
    bg: '{colors.surface}'
    radius: '{radius.md}'
    border: '1px solid {colors.border}'
  input:
    bg: '{colors.surface-light}'
    text: '{colors.text-primary-on-light}'
    radius: '{radius.sm}'
    padding: '11px 15px'
    border: '1px solid {colors.border}'
---

## 1. Visual Theme & Atmosphere
GitHub's design system is a developer-centric, dark-mode-first interface that uses a deep navy background (`#0d1117`) to create high contrast for its primary text (`#f0f6fc`). The typography, led by the `Mona Sans` variable font, is clean and scalable, with large display sizes up to `64px` at a `600` weight for major headings. The aesthetic is defined by its use of "aurora" glows—soft, colored radial gradients and `box-shadow` effects in hues like `#8dd6ff`—that replace traditional shadows for creating depth and highlighting interactive elements.

The visual identity is technical yet polished, balancing dense information displays with generous spacing from a `4px`-based scale. The primary call to action, a vibrant green button (`#5fed83`), stands out against the dark canvas. Subtle CSS animations and canvas-rendered visuals in the hero section provide a sense of dynamism without being distracting. The overall atmosphere is one of precision, functionality, and modern software craftsmanship.

**Key Characteristics:**
*   **Font**: `Mona Sans` for all UI text, from `64px` display to `12px` captions.
*   **Color**: Dark mode foundation (`#0d1117`) with bright green (`#5fed83`) and blue (`#8dd6ff`) accents.
*   **Depth**: No traditional drop shadows; depth is created with colored glows and z-index layering.
*   **Radius**: A tight radius scale, primarily `6px` for controls and `8px` for containers.
*   **Layout**: High-contrast text on dark backgrounds, with ample padding (`32px`+) between sections.
*   **Signature Element**: Aurora-like glows around focused cards and interactive elements.
*   **Motion**: Subtle, fast CSS transitions (`80ms`) on interactive elements like buttons.

## 2. Color Palette & Roles
The palette is built for a dark UI, prioritizing text clarity and scannability with strategic use of vibrant accents for calls-to-action and interactive states.

### Primary
*   **Primary** (`#5fed83`) — A bright, energetic green used for the main "Sign up" call-to-action button.
*   **Primary Dark** (`#08872b`) — A deeper, more saturated green used for secondary positive actions or status indicators like the "Open" badge.

### Accent Colors
*   **Text Accent** (`#8dd6ff`) — A light, accessible blue for hyperlinks and interactive text elements. It's also the base color for focus glows.

### Neutral Scale
*   **Background** (`#0d1117`) — The foundational deep navy/off-black color for the entire page background.
*   **Surface** (`#1f2328`) — A slightly lighter dark gray used for card backgrounds and secondary surfaces to differentiate them from the main background.
*   **Surface Light** (`#f0f6fc`) — An off-white used for the background of light-themed elements like the primary email input field.
*   **Text Primary** (`#f0f6fc`) — The primary off-white text color used across the dark background for maximum readability.
*   **Text Primary on Light** (`#1f2328`) — The primary dark text color for use on light surfaces like the email input.
*   **Text Muted** (`#9198a1`) — A soft gray for secondary or descriptive text, providing clear hierarchy against primary text.

### Surface & Borders
*   **Border** (`#484f58`) — A subtle, low-contrast gray for borders on cards, inputs, and UI dividers.

## 3. Typography Rules
GitHub's typography is built around `Mona Sans`, a modern variable sans-serif that provides excellent legibility at all sizes. The hierarchy is clear and functional, designed for scanning technical content.

*   **Font Family**: `font-family: "Mona Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;`
*   **Monospace Family**: `font-family: "ui-monospace", "Mona Sans Mono", SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;`

### Hierarchy
| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Display** | Mona Sans | 64px | 600 | 1.1 | -1.5px | Hero headline. |
| **Heading 1** | Mona Sans | 48px | 600 | 1.2 | -1px | Major section titles. |
| **Heading 2** | Mona Sans | 40px | 600 | 1.2 | -0.5px | Subsection titles. |
| **Heading 3** | Mona Sans | 22px | 400 | 1.4 | normal | Card titles, smaller headers. |
| **Body** | Mona Sans | 16px | 400 | 1.5 | normal | Default body copy. |
| **Body Large** | Mona Sans | 18px | 400 | 1.6 | normal | Lead paragraphs, descriptive text. |
| **Caption** | Mona Sans | 14px | 400 | 1.5 | normal | Form labels, helper text. |
| **Code/Mono** | ui-monospace | 14px | 400 | 1.5 | normal | For code snippets and monospaced data. |

### Principles
*   **Variable First**: Leverage the `Mona Sans` variable font capabilities for fine-tuned weight and style adjustments where needed.
*   **High Contrast**: Ensure all text maintains strong contrast against the dark background, using `#f0f6fc` as the default.
*   **Functional Sizing**: The type scale is pragmatic, with distinct steps that clearly delineate content hierarchy without being overly expressive.
*   **Generous Line Height**: Line heights of `1.5` or greater on body text ensure long-form content remains readable.

## 4. Component Stylings

### Buttons
GitHub uses a clear hierarchy of buttons: a vibrant green primary CTA, a outlined secondary button, and text-based ghost buttons for navigation.

**Primary Button**
The main call-to-action. Bright, high-contrast, and unmissable.
```css
.btn-primary {
  background-color: var(--color-primary, #5fed83);
  color: var(--color-text-on-primary, #000000);
  font-size: 16px;
  font-weight: 500; /* inferred from screenshot */
  padding: 12px 24px;
  border: 1px solid var(--color-primary, #5fed83);
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: background-color 80ms cubic-bezier(0.33, 1, 0.68, 1), border-color 80ms cubic-bezier(0.33, 1, 0.68, 1);
}

.btn-primary:hover {
  background-color: #72ff97; /* inferred from screenshot */
  border-color: #72ff97; /* inferred from screenshot */
}

.btn-primary:active {
  background-color: #4ace6a; /* inferred from screenshot */
  border-color: #4ace6a; /* inferred from screenshot */
  transition: none;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
```

**Secondary Button**
Used for important but secondary actions, like trying a related product.
```css
.btn-secondary {
  background-color: transparent;
  color: var(--color-text-primary, #f0f6fc);
  font-size: 16px;
  font-weight: 500; /* inferred from screenshot */
  padding: 12px 24px;
  border: 1px solid var(--color-text-primary, #f0f6fc);
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: background-color 80ms cubic-bezier(0.33, 1, 0.68, 1), color 80ms cubic-bezier(0.33, 1, 0.68, 1);
}

.btn-secondary:hover {
  background-color: rgba(240, 246, 252, 0.1);
}

.btn-secondary:active {
  background-color: rgba(240, 246, 252, 0.15);
  transition: none;
}

.btn-secondary:disabled {
  opacity: 0.6;
  border-color: var(--color-border, #484f58);
  color: var(--color-text-muted, #9198a1);
  cursor: not-allowed;
}
```

**Ghost Button / Nav Link**
Used for tertiary actions and navigation links.
```css
.btn-ghost {
  background-color: transparent;
  color: var(--color-text-primary, #f0f6fc);
  font-size: 16px;
  font-weight: 400;
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: color 150ms ease-out, background-color 150ms ease-out;
}

.btn-ghost:hover {
  color: var(--color-text-accent, #8dd6ff);
  background-color: rgba(141, 214, 255, 0.1);
}

.btn-ghost:active {
  background-color: rgba(141, 214, 255, 0.15);
  transition: none;
}
```

### Cards & Containers
Cards have subtle borders and use a glowing effect on hover/focus instead of a traditional shadow.
```css
.card {
  background-color: var(--color-surface, #1f2328);
  border: 1px solid var(--color-border, #484f58);
  border-radius: var(--radius-md, 8px);
  padding: 24px;
  transition: border-color 200ms ease-out, box-shadow 200ms ease-out;
}

.card:hover {
  border-color: var(--color-text-accent, #8dd6ff);
  box-shadow: var(--elevation-glow, 0 0 24px rgba(141, 214, 255, 0.15));
}
```

### Inputs & Forms
Inputs adopt a mixed-theme approach: a light background for clarity and focus, set within the dark UI.
```css
.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-muted, #9198a1);
  margin-bottom: 8px;
}

.form-input {
  background-color: var(--color-surface-light, #f0f6fc);
  color: var(--color-text-primary-on-light, #1f2328);
  font-size: 16px;
  font-weight: 400;
  padding: 12px 16px;
  border: 1px solid var(--color-border, #484f58);
  border-radius: var(--radius-sm, 6px);
  width: 100%;
  transition: border-color 150ms ease-out, box-shadow 150ms ease-out;
}

.form-input:focus {
  border-color: var(--color-text-accent, #8dd6ff);
  outline: 2px solid var(--color-text-accent, #8dd6ff);
  outline-offset: 2px;
  box-shadow: 0 0 12px rgba(141, 214, 255, 0.3); /* inferred from screenshot */
}

.form-input:disabled {
  background-color: var(--color-surface, #1f2328);
  opacity: 0.5;
  cursor: not-allowed;
}
```

### Links
Standard links use the blue accent color for clear affordance.
```css
.link {
  color: var(--color-text-accent, #8dd6ff);
  text-decoration: none;
  transition: text-decoration-color 150ms ease-out;
}

.link:hover {
  text-decoration: underline;
  text-decoration-color: var(--color-text-accent, #8dd6ff);
}

.link:visited {
  color: var(--color-text-accent, #8dd6ff);
}
```

### Badges
Used for status indicators like "Open" or "Closed" on issues.
```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-full, 9999px);
  line-height: 1.5;
}

.badge-status-open {
  background-color: var(--color-primary-dark, #08872b);
  color: var(--color-text-primary, #f0f6fc);
}
```

## 5. Layout Principles

### Spacing System
The system is built on a `4px` base unit, providing a consistent and scalable rhythm for padding, margins, and gaps.
*   **Scale**: `[4, 8, 12, 16, 20, 24, 32, 40, 48, 64]`
*   **Usage Context**:
    *   `4px`: Micro-spacing, icon-to-text gaps.
    *   `8px`: Gaps between related items, small padding.
    *   `16px`: Standard component padding (e.g., inputs).
    *   `24px`: Padding for larger components (e.g., cards), gaps between elements.
    *   `32px`: Gaps between distinct UI groups.
    *   `64px`: Vertical spacing between major layout sections.

### Grid & Container
The layout uses a centered container to keep content focused and readable on large screens.
*   **Max Width**: `1280px`
*   **Columns**: 12-column grid for complex layouts (inferred).
*   **Gutter**: `24px` (inferred).
*   **Section Padding**: `64px` vertically, `24px` horizontally.

### Whitespace Philosophy
Whitespace is used generously to reduce cognitive load and create clear separation between content areas. The dark theme relies on this negative space to guide the user's eye and prevent the UI from feeling cluttered.

### Border Radius Scale
A simple and tight radius scale keeps the UI feeling modern and precise.
*   **`6px` (sm)**: Used for all interactive controls like buttons, inputs, and badges.
*   **`8px` (md)**: Used for larger containers like cards and popovers.
*   **`16px` (lg)**: Used for larger, more prominent containers or media elements.
*   **`9999px` (full)**: Used for pill-shaped elements like status badges.

## 6. Depth & Elevation
GitHub avoids traditional `box-shadow` for depth. Instead, it uses a combination of `z-index` for stacking order and colored glows for visual elevation, particularly on interactive elements. The `z-index` values are sourced directly from the live site.

| Level | Treatment | Use | z-index |
| :--- | :--- | :--- | :--- |
| **Level -1** | Background Glow | Decorative background elements. | -1 |
| **Level 0** | Flat | Default plane for all base content. | 1 |
| **Level 1** | Interactive Surface | Cards, list items on hover/focus. | 2 |
| **Level 2** | Header | The main site navigation header. | 32 |
| **Level 3** | Dropdowns & Popovers | Search suggestions, action menus. | 35 |
| **Level 4** | Overlays | Modals, full-screen overlays. | 99 |

### Shadow Philosophy
The system's "shadows" are not shadows at all, but luminous glows. This approach is ideal for dark UIs, as a soft, colored light source feels more natural than a dark shadow on a dark background. The glow is typically a faint blue (`#8dd6ff`) and is used to signal focus, hover, and other active states, drawing the user's attention.

## 7. Do's and Don'ts

### Do
*   **Do** use `Mona Sans` for all interface text to maintain typographic consistency.
*   **Do** use `#f0f6fc` on `#0d1117` for primary body text to ensure high contrast.
*   **Do** apply the `6px` border radius to all buttons and form inputs.
*   **Do** use the accent color `#8dd6ff` exclusively for links and focus indicators.
*   **Do** use the `4px` spacing scale for all margins and paddings.
*   **Do** use glowing `box-shadow` effects for hover states on cards, not dark drop shadows.
*   **Do** ensure primary CTAs use the bright green `#5fed83` button.
*   **Do** use `#9198a1` for all secondary or non-critical helper text.
*   **Do** use the `#1f2328` surface color for all card backgrounds.

### Don't
*   **Don't** use pure black (`#000000`) for backgrounds; use the deep navy `#0d1117`.
*   **Don't** use a text size smaller than `12px` for any user-facing copy.
*   **Don't** mix multiple border radii on a single component; stick to `6px` or `8px`.
*   **Don't** apply glows to static, non-interactive elements.
*   **Don't** use colors other than `#8dd6ff` for standard hyperlinks.
*   **Don't** create arbitrary spacing values; adhere to the `4px` scale.
*   **Don't** use dark text on the `#5fed83` primary button; its contrast ratio is too low.
*   **Don't** use traditional drop shadows; the elevation model is based on light and z-index.
*   **Don't** underline links by default; the `#8dd6ff` color is sufficient affordance until hover.

### Contrast Audit
*   `#f0f6fc` on `#0d1117` → ratio 17.39, passes AAA. (Primary text on background)
*   `#9198a1` on `#0d1117` → ratio 6.5, passes AA. (Muted text on background)
*   `#000000` on `#5fed83` → ratio 3.25, fails AA for normal text. (Primary button text. **Caution**: requires bold text or a size of at least 18.66px to pass AA).

## 8. Responsive Behavior
The following breakpoints are extracted directly from GitHub's CSS, ensuring an accurate representation of its responsive strategy.

### Breakpoints
| Breakpoint Name | Width | Key Changes |
| :--- | :--- | :--- |
| **Mobile** | < 544px | Single-column layout. Typography scales down. Nav collapses to hamburger menu. |
| **Tablet (Portrait)** | ≥ 544px | Two-column layouts emerge. Horizontal forms become viable. |
| **Tablet (Landscape)** | ≥ 768px | Main navigation may expand. Card grids reflow to 2 or 3 columns. |
| **Desktop** | ≥ 1012px | Full desktop experience. Max-width container is active. Complex layouts with sidebars. |
| **Desktop Large** | ≥ 1280px | Layout expands with more whitespace; no major reflows, just more breathing room. |

### Touch Targets
*   Ensure all interactive elements, especially buttons and links, have a minimum touch target size of `44px` by `44px`.
*   Maintain at least `8px` of space between adjacent touch targets to prevent accidental taps.

### Collapsing Strategy
*   **Navigation**: The primary top navigation collapses into a hamburger menu icon on mobile. The "Sign In" and "Sign Up" buttons remain visible.
*   **Forms**: The hero email input and button stack vertically on screens narrower than `544px`.
*   **Typography**: Display and heading font sizes are reduced by 1-2 steps on mobile to prevent text from dominating the viewport.
*   **Spacing**: Vertical padding between sections (e.g., `64px`) is reduced to `40px` or `32px` on mobile to conserve space.

## 9. Agent Prompt Guide
Use these rules to generate components and layouts that are consistent with the GitHub brand.

*   **Quick Color Reference**:
    *   `primary`: `#5fed83` (CTA Green)
    *   `background`: `#0d1117` (Dark Navy)
    *   `surface`: `#1f2328` (Card Gray)
    *   `text-primary`: `#f0f6fc` (White)
    *   `text-muted`: `#9198a1` (Gray)
    *   `text-accent`: `#8dd6ff` (Blue Link)
    *   `border`: `#484f58` (Subtle Gray)

*   **Iteration Guide**:
    1.  **Always** use `Mona Sans` as the font for all text.
    2.  **Always** set the main page background to `#0d1117`.
    3.  **Always** use `#f0f6fc` for body text and `#9198a1` for secondary text.
    4.  **Always** use `#8dd6ff` for all hyperlinks and do not underline them by default.
    5.  **Always** build primary call-to-action buttons with a `#5fed83` background and `#000000` text.
    6.  **Always** use a `6px` border-radius for interactive elements (buttons, inputs) and `8px` for containers (cards).
    7.  **Always** use values from the `4px` spacing scale: `4, 8, 12, 16, 24, 32, 48, 64`.
    8.  **Never** use traditional `box-shadow`. For elevation on hover/focus, use a blue glow: `box-shadow: 0 0 24px rgba(141, 214, 255, 0.15)`.
    9.  **Always** use a `1px` solid border of `#484f58` on cards and inputs.
    10. **Always** make input fields have a light background (`#f0f6fc`) with dark text (`#1f2328`).
    11. **Always** implement a `:focus` state with a `2px` solid outline of `#8dd6ff`.
    12. **Always** ensure text contrast meets WCAG AA. Be careful with the primary button's text color.