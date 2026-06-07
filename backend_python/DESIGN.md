---
name: ShortVideo
description: A short-video feed platform with playful precision — pink-warm, fast, content-first.
colors:
  blush-pink: oklch(0.62 0.21 4)
  pink-deep: oklch(0.55 0.23 8)
  pink-soft: oklch(0.72 0.17 4)
  pink-light: oklch(0.88 0.07 4)
  pink-mist: oklch(0.97 0.012 10)
  ink: oklch(0.16 0.01 270)
  ink-soft: oklch(0.32 0.01 270)
  muted: oklch(0.52 0.01 270)
  faint: oklch(0.85 0.01 270)
  border: oklch(0.90 0.01 270)
  bg: oklch(0.975 0.006 10)
  surface: "#ffffff"
  surface-hover: oklch(0.97 0.008 10)
  ok: oklch(0.58 0.16 150)
  danger: oklch(0.54 0.21 22)
typography:
  display:
    fontFamily: "Noto Sans SC, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: clamp(1.5rem, 4vw, 2rem)
    fontWeight: 800
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Noto Sans SC, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: clamp(1.2rem, 3vw, 1.5rem)
    fontWeight: 700
    lineHeight: 1.3
  title:
    fontFamily: "Noto Sans SC, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Noto Sans SC, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Noto Sans SC, ui-sans-serif, system-ui, -apple-system, sans-serif"
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.4
rounded:
  sm: 8px
  md: 14px
  lg: 20px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
components:
  button-primary:
    backgroundColor: "{colors.blush-pink}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: 10px 18px
  button-primary-hover:
    backgroundColor: "{colors.pink-deep}"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.sm}"
    padding: 10px 18px
  button-ghost-hover:
    backgroundColor: "{colors.surface-hover}"
  button-danger:
    backgroundColor: oklch(0.97 0.02 22)
    textColor: "{colors.danger}"
    rounded: "{rounded.sm}"
    padding: 10px 18px
  video-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: 0px
  input-field:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: 12px 14px
  pill:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink-soft}"
    rounded: "{colors.full}"
    padding: 5px 12px
---

# Design System: ShortVideo

## 1. Overview: The Playful Terminal

**Creative North Star: "The Playful Terminal"**

ShortVideo is a short-video feed platform disguised as a precision tool. The feed scrolls like a well-tuned terminal: fast, dense, information-first. Every interaction lands in under 150ms. Rounded corners and a soft pink accent are the only hints that this isn't a developer tool — it's a B站-inspired content engine dressed in utilitarian chrome.

The system rejects decorative excess. Pink appears on primary actions, active navigation, and focus rings — nowhere else. Cards are white rectangles on a warm-tinted background. Depth comes from tonal contrast, not shadow. Shadows are reserved for the two moments that genuinely need them: a modal overlay and a toast. Everything else stays flat.

This is a system for scrolling at speed. The user's thumb is the primary input device. Buttons are large enough to tap, transitions are fast enough to never feel like waiting, and loading states are skeletons, not spinners. Content loads, the user reacts, the feed moves on.

**Key Characteristics:**
- One sans-serif family (Noto Sans SC) at five weights, no display/body split
- Pink accent on ≤10% of any screen; its rarity is the point
- 140–160ms transitions with expo-out easing; no orchestrated choreography
- Cards distinguished by tone (white on warm tint), not shadow
- 8px–20px radius scale; softer corners than a pure terminal, sharper than consumer social apps
- Mobile-first with a bottom tab bar; desktop gets a 220px sidebar

**Explicitly rejects:** Enterprise dashboard gray, sterile minimalism, over-commercialized feed badges, glassmorphism, decorative motion, gradient text, side-stripe border accents.

**Future direction:** The pink palette is evolving from high-chroma anime blush toward softer strawberry-milk territory (lower chroma, higher lightness). The current `blush-pink` (oklch(0.62 0.21 4)) anchors the system; a gradual shift to ~oklch(0.75 0.10 4) is the design intent.

## 2. Colors: The Strawberry Milk Palette

A single-accent system. One pink family, one neutral ramp, two semantic colors. The accent's job is to say "this is interactive" — primary buttons, active nav, focus rings. Every other surface stays neutral.

### Primary
- **Blush Pink** (oklch(0.62 0.21 4)): The core accent. Primary buttons, active navigation, link color, focus ring glow. Used on ~5–10% of any given screen. Drives `--pink-gradient` when paired with Pink Deep.
- **Pink Deep** (oklch(0.55 0.23 8)): The gradient anchor. Never used solo; always the deep end of `--pink-gradient`. Provides the 3D depth in the primary button.
- **Pink Soft** (oklch(0.72 0.17 4)): Toast info accent, secondary decorative elements. Lighter and friendlier than the core accent.
- **Pink Light** (oklch(0.88 0.07 4)): Active nav background, hover pre-state for pink actions. The "about to be pink" surface.
- **Pink Mist** (oklch(0.97 0.012 10)): Section backgrounds that need warmth without distraction. Barely perceptible pink tint.

### Neutral
- **Ink** (oklch(0.16 0.01 270)): Body text, headings, primary content. Near-black with a cool-neutral undertone to balance the warm pink.
- **Ink Soft** (oklch(0.32 0.01 270)): Secondary text, button labels, author names. Readable against both white and tinted backgrounds.
- **Muted** (oklch(0.52 0.01 270)): Placeholder text, timestamps, auxiliary metadata. Meets 4.5:1 against white at 15px.
- **Faint** (oklch(0.85 0.01 270)): Skeleton loading bars, scrollbar thumbs. Never used for text.
- **Border** (oklch(0.90 0.01 270)): Card borders, input strokes, dividers. 1–1.5px solid.
- **Background** (oklch(0.975 0.006 10)): Page background. Warm-tinted off-white that creates tonal depth against white cards.
- **Surface** (#ffffff): Card, panel, sidebar, drawer backgrounds. Pure white for maximum contrast against the tinted page.
- **Surface Hover** (oklch(0.97 0.008 10)): Hover state on white surfaces. Subtle warmth that echoes the background tint.

### Semantic
- **OK** (oklch(0.58 0.16 150)): Success states, online indicator dot glow. Green with enough chroma to read as "good" without being neon.
- **Danger** (oklch(0.54 0.21 22)): Error states, delete buttons, destructive action confirmation. Red with warmth that harmonizes with the pink accent.

### Named Rules
**The 10% Rule.** The blush pink accent covers ≤10% of any screen at rest. Its scarcity is what makes it signal "interactive." A screen where pink appears on more than two elements has lost its restraint.

**The Tone-First Depth Rule.** Cards and panels are distinguished from the page background by tonal contrast (white surface on warm-tinted bg), not by box-shadow. Shadows exist for two exceptions: modals/drawers (`shadow-lg`) and toasts (`shadow-lg`). Card hover uses `shadow-sm` at most.

## 3. Typography

**Font:** Noto Sans SC (with ui-sans-serif, system-ui, -apple-system fallback)
**Mono:** ui-monospace, SFMono-Regular, Menlo, Consolas (for code/pre blocks only)

**Character:** A single well-tuned sans-serif at multiple weights. Noto Sans SC's large x-height and open apertures keep text crisp at small sizes (13px labels, 14px metadata). Weight contrast (400 → 700 → 800) does the hierarchy work that a second typeface would in a brand system. No display/body split; one family, five weights, zero distraction.

### Hierarchy
- **Display** (800, clamp(1.5rem, 4vw, 2rem), line-height 1.3, letter-spacing -0.02em): Page titles only. Used on settings, profile, and video detail views. Never on the feed (the feed has no titles).
- **Headline** (700, clamp(1.2rem, 3vw, 1.5rem), line-height 1.3): Section headers in side panels, drawer titles. Modest scale; the content is the star.
- **Title** (700, 18px, line-height 1.3, letter-spacing -0.01em): Video card titles in the feed. Two-line clamp with `-webkit-line-clamp: 2`. The most-read text on the platform.
- **Body** (400, 15px, line-height 1.5): Feed descriptions, comments, profile bios. 15px is the floor; nothing smaller carries running text.
- **Label** (600, 13px, line-height 1.4): Form labels, action button text, timestamps, metadata. The workhorse of the chrome.

### Named Rules
**The No-All-Caps Rule.** Uppercase is prohibited on body text, labels, and buttons. The only exceptions: the logo wordmark and single-character avatar initials. Lowercase and sentence case read faster at scroll speed.

**The Single-Family Rule.** One sans-serif. No serif display, no secondary sans, no handwritten accent. The personality comes from the pink, not the font.

## 4. Elevation

This system uses tonal layering as its primary depth mechanism. White cards (`--surface: #ffffff`) rest on a warm-tinted page background (`--bg: oklch(0.975 0.006 10)`). The 2.5% lightness gap between them is enough to separate surfaces without shadows. Hover states use `--surface-hover` (oklch(0.97 0.008 10)), a fractional warmth shift that indicates interactivity.

Shadows are reserved for three elevated contexts, and each one is a deliberate exception:

### Shadow Vocabulary
- **Card Hover** (`box-shadow: 0 4px 16px rgba(0,0,0,0.05), 0 2px 6px rgba(0,0,0,0.04)`): Applied to video cards on hover only. Light enough to feel like a lift, not a pop. Removed on mouse-out in 200ms.
- **Modal / Drawer** (`box-shadow: 0 12px 40px rgba(0,0,0,0.07), 0 4px 12px rgba(0,0,0,0.05)`): Drawer, modal backdrop content, and the toast wrapper. The only "real" shadow in the system. Says "this surface is above everything."
- **Primary Button Rest** (`box-shadow: 0 2px 8px oklch(0.62 0.21 4 / 0.28)`): The pink glow under the primary button. Not a structural shadow; a brand accent that gives the gradient button physical presence.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. Shadows are applied only as a response to state (hover, modal overlay, toast). If a card has a permanent shadow, it's wrong.

**The Two-Shadow Ceiling.** Only two distinct shadow tokens (`--shadow` for hover, `--shadow-lg` for overlay). No intermediate values, no custom one-off shadows. If `--shadow-lg` isn't enough, the element doesn't need more shadow; it needs a different elevation strategy (backdrop blur or darker scrim).

## 5. Components

Every interactive component has: default, hover, focus-visible, active, and disabled states. Loading states use skeleton placeholders, not spinners. The component vocabulary is small: buttons, inputs, cards, pills, nav items, toasts, avatars. Nothing exotic.

### Buttons
- **Shape:** Softly rounded (8px radius). Straight edges belong to terminals; these are slightly curved to signal "tap me."
- **Primary:** Pink gradient background (`--pink-gradient`: 135deg from Blush Pink to Pink Deep), white text, 700 weight, 10px 18px padding. Glow shadow at rest, lifts on hover (translateY(-1px) + shadow intensifies). Presses scale to 0.96 instantly. Transition: 140ms expo-out.
- **Ghost:** Transparent background, Ink Soft text, no border. Hover fills with Surface Hover. Used for secondary actions, toolbar icons, and comment drawer close.
- **Danger:** Warm red tint background (oklch(0.97 0.02 22)), Danger text, warm border (oklch(0.90 0.02 22)). Hover deepens the red tint. Used for delete and destructive actions.
- **Disabled:** 0.45 opacity, cursor not-allowed, no pointer events. Applied uniformly across all variants.
- **Focus-visible:** Pink glow ring (3.5px, oklch(0.88 0.07 4 / 0.5)) on all variants. The same ring appears on focused inputs for consistency.

### Video Cards
- **Shape:** 20px radius (the softest corner in the system). Overflow hidden to clip the cover image.
- **Cover:** 16:9 aspect ratio, image fills with object-fit cover. Hover scales the image 3% over 300ms. A semi-transparent play icon (▶) fades in on hover.
- **Body:** 14px 16px padding, vertical stack with 8px gap. Title (15px, 700, two-line clamp), author row (avatar + username, 13px), metadata row (date, 13px muted), action row (like/comment buttons, 13px).
- **Hover:** Shadow-sm appears, cover image zooms, play icon fades in. Transition: 200ms.
- **Responsive:** Below 640px, padding shrinks to 12px, title to 14px.

### Navigation
- **Desktop Sidebar:** 220px fixed left panel, white surface with right border. Logo at top (pink gradient, 17px, 900 weight). Nav links below: 14px, 500 weight, 8px radius, Ink Soft default → Surface Hover on hover → Pink Light background + Blush Pink text when active. User section at bottom with avatar + username + online dot.
- **Mobile Bottom Tabs:** 56px tall bar, white surface with top border, grid of equal columns. Icons (20px emoji) + labels (13px). Muted default → Pink active. Includes safe-area padding.
- **Breakpoint:** 768px. Above = sidebar. Below = bottom tabs.

### Inputs & Fields
- **Style:** 1.5px Border stroke, Background fill, 8px radius, 12px 14px padding, 15px font size.
- **Focus:** Border shifts to Blush Pink, a 3.5px pink glow ring appears (oklch(0.88 0.07 4 / 0.5)). Transition: 160ms on border-color and box-shadow.
- **Textarea:** Same treatment, with 14px font size and larger radius (14px) for the comment input.
- **Placeholder:** Muted color (oklch(0.52 0.01 270)). Meets 4.5:1 contrast against the Background fill.

### Pills & Chips
- **Style:** Full-round (9999px radius), 5px 12px padding, 13px 500 weight. Default: Background fill + Border stroke + Ink Soft text.
- **Success variant:** Green tint background (oklch(0.95 0.04 150)), green border (oklch(0.85 0.08 150)), green text (oklch(0.45 0.12 150)).
- **Danger variant:** Red tint background (oklch(0.95 0.04 22)), red border (oklch(0.88 0.06 22)), Danger text.

### Toast
- **Position:** Fixed, centered top, z-index 200. Slides down 12px on enter (300ms expo-out).
- **Style:** White surface, 14px radius, 14px 16px padding, shadow-lg. 3px left border for type: OK green, Danger red, Info pink-soft.
- **Icon:** 24px circle with type-colored background + white checkmark/cross/dot.
- **Dismiss:** Click to dismiss. No auto-dismiss timer.

### Avatar
- **Style:** Full-round, overflow hidden, subtle shadow (0 2px 8px rgba(0,0,0,0.06)).
- **Image mode:** Object-fit cover on provided src.
- **Generated mode:** Deterministic gradient from username hash (hue rotates across 360°, two-stop gradient 135deg). White initial letter centered, 800 weight, 55% font size.
- **Sizes:** 24px (comment author), 28px (comment list), 32px (sidebar user), 40px (profile).

### Skeleton Loading
- **Style:** Shimmer animation (1.4s infinite), gradient from Border → Faint → Border, 200% background-size sliding horizontally.
- **Shape:** Matches the content it replaces (text line = 8px radius bar, card = 14px radius rectangle, avatar = full-round circle).
- **Rule:** Every async-loaded content area ships with a skeleton variant. No spinners in content areas.

## 6. Do's and Don'ts

### Do:
- **Do** use the pink accent on ≤10% of any screen. Primary buttons, active nav, focus rings, links. Nothing else.
- **Do** distinguish cards from the background via tonal contrast (white on warm tint), not box-shadow. Shadows are for hover and overlay states only.
- **Do** use 140–160ms expo-out transitions for interactive state changes. Speed is part of the personality.
- **Do** use skeleton loaders for all async content. The shimmer animation signals "content is coming" without breaking the feed's visual rhythm.
- **Do** use the single Noto Sans SC family for all text. Hierarchy comes from weight (400/500/600/700/800) and size, not font changes.
- **Do** keep the feed dense. Author info, stats, and actions pack into a compact card. Information-rich without feeling cluttered — the B站 lesson.
- **Do** make every interactive element respond to hover, focus, active, and disabled states. A button without `:active` feedback feels broken.

### Don't:
- **Don't** use box-shadow on static cards. Cards are flat at rest. If a card needs to stand out, use a border or a background tint.
- **Don't** use gradient text (`background-clip: text`). Emphasis comes from weight and size, not decorative fills.
- **Don't** use glassmorphism or backdrop-filter blur for decorative effect. The feed is the content; the chrome is invisible.
- **Don't** add all-caps labels, eyebrow text, or numbered section markers (01 / 02 / 03). This is not a marketing page.
- **Don't** use side-stripe borders (`border-left` > 1px as a colored accent) on cards or callouts. Use full-border, background tint, or nothing.
- **Don't** invent new button styles per screen. Primary, ghost, and danger are the only three. Consistency beats creativity.
- **Don't** use spinners in content areas. Skeleton loaders only. Spinners are for full-page initial loads.
- **Don't** let pink appear on more than two non-content elements at once. If the sidebar nav, a card action, and a focus ring are all pink simultaneously, the accent has lost its signal value.
- **Don't** design for desktop first. The mobile bottom-tab + scroll layout is the primary experience. Desktop sidebar is an enhancement, not the default.
- **Don't** use enterprise/admin dashboard aesthetics: gray tables, form-heavy layouts, conservative typography, muted palettes. This is B站, not Jira.
