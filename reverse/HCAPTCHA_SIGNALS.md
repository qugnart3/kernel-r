# hCaptcha Fingerprint Signals — Full Analysis

## Source
- `hcaptcha.html` (698KB iframe) — version `221126bfaff10f69f5e2c60a7ff42e4b9f16aed7`
- `api.js` (420KB outer frame)
- VM bytecode: 63,533 opcodes, 4,106 decoded strings from string table

## Architecture
hCaptcha uses a **custom stack-based VM bytecode interpreter** to collect fingerprints.
Property names are stored as base64-encoded, URI-encoded, char-shifted strings in `_eEubans8`.
This makes static analysis of property access nearly impossible without decoding the bytecode.

The VM has these registers:
- `_sqgIzP` — instruction pointer
- `_SvT3ooH6r` — flags/mode register
- `_1SaXxmI` — operand stack
- `_9sogX7` — local variables
- `_Na8uGFJH` — scope chain
- `_FFOciPLPb` — bytecode array
- `_eEubans8` — encoded string table
- `_0udpYPiXVw` — `this` context (starts as `window`)

Key opcodes:
- 6: `window[pop()]` — dynamic window property access
- 22: decode string from table (base64 + URI decode + char shift)
- 25: function call
- 39: property access `obj[key]` with auto-bind

## Data Flow
1. **Checkbox click** → `Xi.getData()` (motion manifest) + `Br.collect()` (automation flags) sent via `checkbox-selected` message
2. **getcaptcha POST** → includes `motionData` (from `On.getData()` in api.js) + `vmdata` (from `Mn()` VM execution)
3. **checkcaptcha POST** → includes full `motionData` with `topLevel` (checkbox-frame data), answers, proof-of-work `n`

## Browser Fingerprint Properties Collected

### Screen / Display
- `screen` (the object)
- `width`, `height` — screen dimensions
- `availWidth`, `availHeight` — available screen
- `colorDepth` (via `screen` object)
- `devicePixelRatio` — DPR (direct + via `window`)
- `innerWidth`, `innerHeight` — viewport
- `outerWidth`, `outerHeight` — browser window
- `screenX`, `screenY` — window position
- `offsetLeft`, `offsetTop`
- `clientWidth`, `clientHeight`
- `mozInnerScreenX`, `mozInnerScreenY` — Firefox-specific

### Navigator / Hardware
- `hardwareConcurrency` — CPU cores (accessed via VM string "Memory" context or direct)
- `deviceMemory` — RAM (via navigator, not in string table but accessed via VM computed property)
- `platform` — OS string
- `userAgent` — UA string (8 refs in hcaptcha.html)
- `maxTouchPoints` — touch capability
- `plugins` — plugin list (6 refs)
- `languages` — language list

### Timing / Performance
- `performance` — Performance API
- `getEntriesByType` — resource timing
- `startTime`, `duration` — timing entries
- `now` — high-res timestamp
- `Date` — date constructor

### DOM / Automation Detection
- `getElementById`, `getElementsByTagName`, `querySelector`, `querySelectorAll` — hooked by `Mt()` to collect stack traces
- `__zone_symbol__OriginalDelegate` — Zone.js detection (Angular/automation)
- `Reflect`, `Proxy` — Reflect/Proxy detection (automation frameworks)
- `chrome` — chrome object presence (6 refs)
- `Error.stackTraceLimit` — stack manipulation detection
- `webkitMatchesSelector`, `msMatchesSelector` — browser compat
- `MutationObserver` — DOM mutation monitoring
- `extension://` — browser extension detection
- `/headless` — headless browser detection
- `callbackCount` — callback enumeration
- `/await` — async detection pattern

### WebGL / Canvas
- `CANVAS` — canvas element
- Accessed via `getParameter` with GPU constants (VM-computed, not as strings)
- `processImage` — canvas image processing
- `cssRules`, `styleSheets` — CSS fingerprinting

### Input / Behavioral Telemetry
Event listeners (from api.js + hcaptcha.html):
- `mousemove` (5+), `mousedown` (7), `mouseup`, `mouseenter`, `mouseleave`
- `keydown` (20), `keyup` (4)
- `touchstart` (14), `touchmove` (9), `touchend`, `touchcancel`
- `pointermove` (3), `pointerdown`, `pointerup`, `pointerId`, `pointerType`
- `devicemotion` (4) — accelerometer: `acceleration`, `rotationRate`, `gamma`
- `scroll` (25)
- `click`, `dblclick`, `focus`, `blur`
- `paste`, `copy` — clipboard events

Motion data fields collected by `_i` (Xi):
- `timeBuffers` — time-series motion data with mean periods
- `lpt` — last pointer time
- `st` — start time
- `loadTime` — page load time
- `tc` — container reference
- `v` — version (1)
- `topLevel` — cross-frame motion data

### Storage / State
- `localStorage` — local storage
- `getItem`, `setItem`, `removeItem` — storage ops
- `cookie` — cookie access (via `Ye.hasCookie`)
- `sessionStorage` (implicit)

### Network / Location
- `location`, `hostname`, `href`, `pathname`, `origin`
- `hashchange`, `popstate` — navigation events
- `history`, `pushState`, `replaceState` — SPA navigation
- `postMessage` — cross-frame communication

### Crypto
- `crypto`, `subtle` — Web Crypto API
- `getRandomValues` — CSPRNG
- `importKey`, `encrypt`, `decrypt`, `deriveUint32`
- `AES-GCM` — encryption algorithm
- `WebAssembly`, `instantiate`, `compile`, `Module`, `Instance` — WASM for proof-of-work

### Miscellaneous
- `visualViewport` — viewport API
- `requestIdleCallback`, `cancelIdleCallback` — idle detection
- `visibilitychange` — tab visibility
- `contenteditable` — editable elements
- `matchMedia` — media queries (6 refs, used for DPR and feature detection)
- `DOMContentLoaded` — page load
- `readyState` — document state

## Cross-Check Signals (Why Toggles Get Flagged)

### locale_tz (BIGGEST RED FLAG)
- Timezone is cross-checked against IP geolocation
- `location.hostname` + `origin` sent alongside timezone data
- Server-side: vmdata returned by server includes expected timezone for IP
- **Fix needed:** Match timezone to IP's actual geo, OR use proxy matching the timezone

### screen (FLAGGED)
- `innerWidth`/`innerHeight`/`outerWidth`/`outerHeight`/`devicePixelRatio` NOT patched in KernelR
- These leak real values while `screen.width`/`screen.height` are spoofed
- hCaptcha checks: `screen.width` vs `outerWidth`, `screen.height` vs actual DPR
- `matchMedia` queries can detect real DPR
- `screenX`/`screenY` window position checked for consistency
- **Fix needed:** Patch innerWidth/outerWidth/outerHeight/innerHeight + devicePixelRatio + matchMedia

### fonts (FLAGGED)
- Font enumeration via CSS `@font-face` + measureText
- KernelR whitelist is only 17 fonts; normal systems have 150+
- Too few fonts = fingerprint anomaly
- **Fix needed:** Expand whitelist to 60-80+ common fonts

### cpu_memory (FLAGGED when combined)
- `hardwareConcurrency` + `deviceMemory` cross-checked with GPU capability tier
- A 2-core CPU with a high-end GPU is suspicious
- `Memory` keyword found in VM strings — dedicated memory probe
- **Fix needed:** Ensure CPU/memory values are consistent with GPU tier

### T8/T9/T10 (NOT FLAGGED — safe)
- Canvas (T8): Adds noise, no inconsistency to detect
- WebGL (T9): Spoofs vendor/renderer, but values exist in real hardware
- Audio (T10): Adds noise, no inconsistency to detect
- These work because they ADD variation rather than CREATE inconsistencies

## Automation Detection (Br.collect / Mt)

The `Mt()` function hooks:
- `document.getElementById`
- `document.querySelector`
- `document.querySelectorAll`
- `document.getElementsByTagName`

These collect **stack traces** of callers. Automation tools (Puppeteer, Playwright, CDP) create distinctive stack traces from their injection scripts.

`Br.collect()` returns an array `Vt` of collected automation signals.

Additional automation checks:
- `chrome` object structure (6 probes)
- `Proxy` / `Reflect` presence and behavior
- `Error.stackTraceLimit` manipulation
- `__zone_symbol__OriginalDelegate` (Zone.js)
- `extension://` in stack traces
- `/headless` path detection
- `webkitPersistentStorage` (deprecated API presence)

## MCP (Motion Context Protocol) — Behavioral Analysis

hCaptcha's new behavioral system found in the VM strings:
- `mcpBuffer` — motion capture buffer
- `mcpCaptureStart` / `mcpCaptureEnd` / `mcpCaptureAvailable`
- `mcpEventCleanups` — cleanup handlers
- `mcpJourneySites` — cross-site journey tracking
- `mcpListenersActive` — active listener tracking
- `mcpTruncations` — data truncation tracking
- `setWebMcpJourney` — journey state setter
- `bm:mcpc` / `bm:mcpr` — MCP capture/restore events
- `bm:cfbt` — first byte time
- `bm:mo` / `bm:mod` — mutation observer data
- `bm:pnfe` — new form elements

This tracks the user's **entire journey across the site**, not just the captcha interaction.
It monitors form interactions, navigation patterns, and page mutations.

## Form / Context Intelligence

hCaptcha identifies what the page is for:
- Login detection: `/login`, `/login/`, `password`, `current_password`, `sign in`, etc.
- Registration: `/register`, `/signup`, `create account`, `create_account`
- Payment: `checkout`, `purchase`, `buy now`, `payment`, `cc-number`, `cc-csc`
- Password reset: `/login/forgot-password`, `reset password`, `recover password`
- Search: `search`, `searchbox`, `search_query`

This context affects the risk model — a bot on a login page is scored differently than on a search page.

## Proof-of-Work (HSW)

The `cr()` function sends to a Web Worker:
- `href` — page URL
- `ardata` — challenge data
- `vm_data` — server-provided VM data
- `uj_data` — user journey data
- `errors` / `messages` — accumulated errors

Uses WebAssembly for computation, result is the `n` parameter in getcaptcha/checkcaptcha.

## Key Collection Functions (Non-VM, Plain JS)

### `q.prototype.getScreenDimensions()`
```js
for (var e in window.screen) t[e] = window.screen[e];
delete t.orientation;
```
Dumps ALL screen properties including width, height, availWidth, availHeight, colorDepth, pixelDepth.

### `q.prototype.interrogateNavigator()`
```js
for (var i in window.navigator)
  if ("webkitPersistentStorage" !== i)
    try { var n = window.navigator[i]; JSON.stringify(n); e[i] = n; }
```
Dumps ALL navigator properties: hardwareConcurrency, deviceMemory, language, languages, platform, userAgent, maxTouchPoints, connection, etc.
Also enumerates `navigator.plugins[].filename`.

### `Q.dpr()`
```js
window.devicePixelRatio || 1
```

### `q.prototype.getWindowDimensions()`
```js
return [this.width(), this.height()]
// width = Math.min(window.innerWidth, document.documentElement.clientWidth)
```

### `q.prototype.getOrientation()`
```js
matchMedia("(orientation: landscape)").matches
```

### Cross-checks in `Q` constructor:
- `"ontouchstart" in window` — touch capability
- `navigator.maxTouchPoints > 0` — touch points
- `navigator.msMaxTouchPoints > 0` — IE touch
- Mobile detection: touch + OS name in [iOS, Windows Phone, Android, BlackBerry]

## Summary: What KernelR Must Fix

| Priority | Issue | Toggle | Fix |
|----------|-------|--------|-----|
| P0 | Timezone ↔ IP mismatch | locale_tz | Match TZ to IP geo, or use geo-matched proxy |
| P0 | innerWidth/outerWidth leak real values | screen | Patch LocalDOMWindow::innerWidth/outerWidth/outerHeight/innerHeight |
| P0 | devicePixelRatio not patched | screen | Patch LocalDOMWindow::devicePixelRatio |
| P0 | matchMedia leaks real DPR | screen | Override matchMedia resolution queries |
| P1 | Font whitelist too small (17) | fonts | Expand to 60-80 common fonts |
| P1 | CPU/Memory ↔ GPU inconsistency | cpu_memory | Profile generator must create consistent combos |
| P2 | screenX/screenY leak | screen | Consider patching |
| P2 | mozInnerScreenX/Y (Firefox only) | N/A | Not needed for Chrome fork |
| P3 | MCP journey tracking | N/A | Natural browsing behavior; hard to fake |
