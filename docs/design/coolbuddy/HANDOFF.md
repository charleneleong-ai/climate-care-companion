# Handoff: CoolBuddy — Climate Emergency AI Assistant (Mobile)

## Overview
A mobile app prototype for an AI assistant, "CoolBuddy," that helps a vulnerable, elderly user (Margaret, UK-based) stay safe during extreme heat and cold. It shows a personal risk read on the weather, one-tap guidance, a one-tap call to a trusted person, a voice assistant, scheduled check-ins that escalate to a caregiver if unanswered, a caregiver-facing view, and a settings screen with onboarding.

## About the Design Files
The files in this bundle (`Neighbor.dc.html`, `Avatar.dc.html`, `ios-frame.jsx`) are **design references built in HTML/JS** — prototypes of the intended look, content, and interaction flow. They are not production code to copy directly. The task is to **recreate these designs in the target codebase's environment** (React Native, Swift/SwiftUI, Kotlin/Compose, Flutter, etc.) using that codebase's existing patterns, navigation, and component libraries. If no mobile framework exists yet in the target repo, choose the framework best suited to the team's stack and implement the designs there.

## Fidelity
**High-fidelity.** Colors, type, spacing, copy, and animation timing shown are final-intent and should be recreated precisely (adjusted only for native platform conventions, e.g. iOS/Android system fonts and safe areas).

## Screens / Views

### 1. Onboarding (6 steps, dot progress indicator + Skip)
- Step 0 — Welcome: CoolBuddy avatar (centered, animated float), "Hi, I'm CoolBuddy.", intro copy.
- Step 1 — Name/age/address text fields (display-only in prototype; wire to real inputs).
- Step 2 — Multi-select chips: personal risk factors ("I live on my own", "No air conditioning", "I take a water pill", "Stairs are hard for me", "I use oxygen at home").
- Step 3 — Emergency contacts list with call order (First/Second/Third) + "Add someone else".
- Step 4 — Check-in time toggles (10am, 3pm) + note about extra check-ins on dangerous days.
- Step 5 — Confirmation: "You're all set, Margaret." with avatar.
- Nav: Back (steps 1–5) + primary CTA button whose label changes per step ("Nice to meet you" → … → "Take me in"). Final tap routes to Home.

### 2. Home (weather-style)
- Full-bleed background tinted by current condition (cold / just right / warm / dangerously hot) or a neutral theme (see Design Tokens/Theme below).
- Header: date/time, settings gear button (top right).
- Large temperature display (tap toggles °F/°C), headline (e.g. "Too hot to stay put"), one-line explanation.
- Center: circular animated "face" that changes expression by condition (happy / heat-strained with a sweat drop / shivering) — see Design Tokens.
- CoolBuddy avatar bubble, bottom-right, floating animation, opens Voice screen.
- Two full-width primary actions stacked: "What do I do now?" (filled) and "Call a person" (outlined) — these are the **only two** primary actions on Home, per product requirement.

### 3. What do I do now (action plan)
- Back button, big title + explanatory line, numbered 3-step card list (each: icon circle with number, title, body).
- Footer: "Done. Check on me later" (routes to Check-in) and "Ask CoolBuddy something else" (routes to Voice).

### 4. Call a person
- Back button, title, list of one-tap contact rows (avatar initial, name, role, green call-affordance dot). Includes trusted contacts, CoolBuddy voice line, and 999.

### 5. Voice (CoolBuddy assistant)
- Dark background (#221C18, fixed — not theme-dependent).
- CoolBuddy avatar, larger, animated halo + floating.
- Current spoken line (Newsreader serif, large).
- Animated listening waveform bars.
- Two suggested-question buttons that populate the spoken line on tap ("I feel dizzy", "Is it safe to go outside?").
- Close (✕) returns Home.

### 6. Settings
- Back button + title.
- Profile card (avatar initial, name, age, address).
- Temperature unit toggle (Fahrenheit / Celsius segmented control).
- Risk factors (same chip list as onboarding step 2, editable here).
- Your people (contact list, same as onboarding step 3, read-only display in prototype).
- How I reach you (4 toggle rows: twice-daily check-in, more check-ins on risky days, read aloud, notify contact after 2 missed).
- **Look** (theme picker, 3 options — see Theme below).
- **Assistant icon** (avatar style picker: Person / Girl / Earth — segmented control).
- Language (English / Español / 中文 segmented control).
- "Show me the setup again" link returns to onboarding.

### 7. Check-in
- Full-bleed themed background (uses current theme ink/sky colors, not a fixed blue).
- Big friendly prompt ("Margaret, how are you doing?"), explanation of the 15-minute/escalation timer.
- Two large buttons: "I'm okay" (filled) routes Home; "I need help" (outlined) routes to Escalating.
- Status line: "No answer for 12 minutes" (demo state).

### 8. Escalating (no answer)
- Full-bleed dark themed background (ink color), "Getting help" pill badge, headline, explanation.
- List of contacts being reached with live status (No answer / Notified / Asked to knock / Waiting), each with a status-colored dot.
- CTA: "See what Dana receives" (routes to caregiver view) and "I'm fine, stop this" (routes Home).

### 9. Caregiver view (Dana's phone)
- Neutral light background — this screen is intentionally NOT theme-tinted (different device/person).
- Alert card (red header "Mum needs a check · 3:27pm"), summary text, key facts table (last active, indoor temp, outside temp/warning, nearest cool place).
- Actions: Call Mum, Ask Ruth next door to knock, Request a welfare check (red-tinted, most urgent).
- Back link returns to Margaret's Home.

## Interactions & Behavior
- Tapping the temperature toggles °F/°C app-wide; all copy re-renders with converted values.
- Home's two-button rule is fixed: never add more primary actions to Home.
- Risk-factor and check-in-preference selections are simple multi-toggle state (array of indices in the prototype).
- Voice screen suggested questions replace the spoken line inline (simulated; wire to a real assistant response in production).
- Chat/voice line delivery in the earlier chat prototype used a simulated 900ms "typing" delay — carry this pattern if a text chat mode is retained.
- Animations (CSS keyframes in the prototype, translate to native equivalents):
  - `nb-bob`: gentle float, 3–5s ease-in-out infinite, translateY ±9px.
  - `nb-halo`: pulsing glow ring, scale 1 → 1.3, opacity 0.5 → 0, speeds tied to severity (1.5s at extreme heat down to none when neutral).
  - `nb-shimmer`: background glow opacity pulse, 2.4–12s depending on severity.
  - `nb-shiver`: cold-state face micro-shake, 0.28s ease-in-out infinite, translateX ±1.5px.
  - `nb-drip`: heat-state sweat drop, 2.2s, translateY 0→22px with fade.
  - `nb-listen`: voice waveform bars, scaleY 0.3→1, staggered per bar.
  - `nb-blink`: avatar eye blink, ~6s cycle, scaleY dip to 0.12 briefly.
  - Animation speed scales with severity: neutral/good = slow or none, extreme heat = fastest/most animated (product requirement: "more animated" at higher heat).
- Escalation logic (as specified by product): both automatic and manual paths exist — the app auto-escalates (calls contact) on missed check-ins, AND the assistant/user can manually trigger "I need help" — behavior varies by severity level.

## State Management
- `screen`: current view id (see screens above).
- `mood`/`condition`: cold | good | hot | extreme — drives colors, copy, temps, animation speed.
- `unit`: F | C — persisted toggle.
- `theme`: "Full color by temperature" | "Neutral beige and white" | "Neutral with color edge" — user-selectable in Settings.
- `avatarStyle`: "Person" | "Girl" | "Earth" — user-selectable in Settings.
- `traits`: selected indices of personal risk factors.
- `prefs`: selected indices of check-in/notification preferences.
- `lang`: selected display language.
- `ob`: current onboarding step index (0–5).
- Voice screen: last spoken line (string), updates on suggested-question tap.

## Design Tokens

### Typography
- Headings/UI: **Signika** (weights 400–700).
- Long-form/explanatory copy: **Newsreader** (serif, regular/medium, sometimes italic-capable), used for the warmer, human-voiced sentences throughout.
- Minimum body size 16–18px; large numerals (temperature) at 104px on Home.

### Colors by condition (theme = "Full color by temperature")
- **Cold**: sky `#DCE9F2`, ink `#1B4666`, ink-soft `#4E738F`, face `#BFD9EA`, accent dot `#3C7CA8`.
- **Just right**: sky `#DFF0DC`, ink `#2C4E39`, ink-soft `#5C7062`, face `#C4E2C0`, accent dot `#5C9B6B`.
- **Warm**: sky `#FBE9D6`, ink `#8A4416`, ink-soft `#A5714A`, face `#F6D3AC`, accent dot `#D9832F`.
- **Dangerously hot**: sky `#F9D6C4`, ink `#7A2A0E`, ink-soft `#9E5837`, face `#F4B191`, accent dot `#B93712`.
- Alert/urgent accent (used sparingly, e.g. escalation CTA, red facts): `#C2521F` / `#A44317` / dark backdrop `#2A1710`.
- Caregiver view neutral palette: background `#F5F1EC`, card `#FFFFFF`, alert header `#C2521F`.
- Voice screen fixed dark backdrop (not theme-tinted): `#221C18`, card `#2C231D`, border `#423428`.

### Theme variants (Settings → Look)
- **Full color by temperature** (default): backgrounds/ink/face colors shift per condition as above.
- **Neutral beige and white**: sky `#FBF6EE`, ink `#2A2320`, ink-soft `#6E635C`, face `#EFE1CD` — flat regardless of condition; no glow/shimmer/halo animation.
- **Neutral with color edge**: same neutral palette, plus a 10px outer border around the device frame in the condition's accent dot color (transitions on condition change).

### Avatar (Settings → Assistant icon)
- Three interchangeable illustrated variants sharing the same warm-orange-to-cool-blue ring treatment: **Person**, **Girl**, **Earth** (globe). Rendered via a shared `Avatar.dc.html` component parameterized by style, reused at three sizes: small (Home float, ~84px), medium (onboarding, ~172px), large (Voice screen, ~190px).

### Spacing/shape
- Card radius: 16–22px. Primary buttons: 20–22px radius, min-height 70–88px (large touch targets for elderly users).
- Screen padding: ~20–26px horizontal.
- Minimum tap target: 44px+ (settings toggles, back buttons), primary CTAs 70px+.

### Locale (UK)
- Times in lowercase am/pm (e.g. "1:48pm"), Celsius-first-friendly (unit defaults to °C), addresses use UK format ("Flat 3C, 412 Wilson Road, Manchester"), emergency number **999** (not 911), NHS 111 in place of a US "211" reference, "Mum" not "Mom", "flat" not "apartment", "neighbour" not "neighbor" in copy (app name itself, CoolBuddy, is unaffected).

## Assets
No external image assets — all illustration (weather face, CoolBuddy avatar variants) is built from CSS shapes/gradients in the prototype. A production build should commission real vector illustration for the avatar (Person/Girl/Earth) and the weather face states to the same expressive, friendly spec.

## Files
- `Neighbor.dc.html` — main app prototype, all 9 screens, state logic, theme and avatar tweaks.
- `Avatar.dc.html` — shared avatar component (Person/Girl/Earth variants).
- `ios-frame.jsx` — iOS device bezel used only for prototype presentation; not part of the product UI.
