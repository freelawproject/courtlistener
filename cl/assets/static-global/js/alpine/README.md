# Alpine JS in CourtListener

This directory contains both Alpine upstream code (core + plugins) and our custom Alpine components/composables.

| Path                    | Ownership   | Notes                                                                 |
|-------------------------|-------------|-----------------------------------------------------------------------|
| `alpinejscsp@<version>` | Upstream ⚠️ | Alpine core (CSP build).                                              |
| `plugins/*`             | Upstream ⚠️ | Official Alpine plugins.                                              |
| `components/*`          | Ours        | Our custom Alpine components. Each corresponds to a Cotton component. |
| `composables/*`         | Ours        | Our reusable Alpine logic, not tied to a particular component.        |

## Important

⚠️ Upstream files in this directory should never be edited directly.
