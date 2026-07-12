# Alpine JS in CourtListener

This directory contains both Alpine upstream code (core + plugins) and our custom Alpine components/composables.

| Path                    | Ownership   | Notes                                                                 |
|-------------------------|-------------|-----------------------------------------------------------------------|
| `alpinejscsp.*`         | Upstream ⚠️ | Alpine core (CSP build).                                              |
| `plugins/*`             | Upstream ⚠️ | Official Alpine plugins.                                              |
| `components/*`          | Ours        | Our custom Alpine components. Each corresponds to a Cotton component. |
| `composables/*`         | Ours        | Our reusable Alpine logic, not tied to a particular component.        |

## Upstream sources

Current version: **3.15.9**

| Package | CDN URL |
|---------|---------|
| `@alpinejs/csp` | https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.15.9/dist/cdn.js |
| `@alpinejs/anchor` | https://cdn.jsdelivr.net/npm/@alpinejs/anchor@3.15.9/dist/cdn.js |
| `@alpinejs/collapse` | https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.15.9/dist/cdn.js |
| `@alpinejs/focus` | https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.15.9/dist/cdn.js |
| `@alpinejs/intersect` | https://cdn.jsdelivr.net/npm/@alpinejs/intersect@3.15.9/dist/cdn.js |
| `@alpinejs/ui` | https://cdn.jsdelivr.net/npm/@alpinejs/ui@3.15.9/dist/cdn.js |

`.min.js` variants are available at the same paths with `cdn.min.js`.

## Important

⚠️ Upstream files in this directory should never be edited directly.
