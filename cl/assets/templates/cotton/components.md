# Cotton Components Reference

This document catalogs all reusable Cotton components available in CourtListener. Use these components to build consistent, accessible UI.

**Stack**: Django Cotton + AlpineJS + Tailwind CSS

**Availability**: All components work automatically in templates extending `new_base.html` - no imports needed.

---

## Text & Content

### `c-eyebrow`
Small, uppercase label text for section headers or categories.

**Props**: None
**Slots**: Default - text content

```html
<c-eyebrow>CourtListener</c-eyebrow>
```

---

### `c-code`
Code block with optional copy-to-clipboard. Uses `<pre>` tags (preserves whitespace).

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `disable_copy` | No | Hides the copy button. Default: false |
| `class` | No | CSS classes for the `<pre>` element |

**Slots**: Default - code content

```html
<c-code disable_copy>
const example = "hello";
</c-code>
```

---

### `c-copy-to-clipboard`
Unstyled button that copies text to clipboard on click, Enter, or Space.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `text_to_copy` | Yes | Text to copy. Escape special chars with HTML entities or `escapejs` filter |
| `class` | No | CSS classes for styling |

**Slots**: Default - button content/label

```html
<c-copy-to-clipboard
  text_to_copy="Text to copy here"
  class="btn-outline"
>
  Click to copy
</c-copy-to-clipboard>
```

---

### `c-two-column-list`
Renders items in a two-column layout. Items can be plain text, dict values, or links.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `list` | Yes | Array of strings or dicts. Dicts with both `href` and `label` render as links |
| `key` | No | Dict key to display for non-link dict items |
| `link_class` | No | CSS classes for links (recommend `underline` for a11y) |
| `responsive` | No | Collapses to one column on small screens |
| `class` | No | Container classes (appended to `w-full flex flex-row justify-between`) |

**Slots**: None

```html
<c-two-column-list
  key="name"
  link_class="underline"
  responsive
  :list="[
    {'name': 'Plain dict value'},
    {'href': '/example', 'label': 'Link item'},
    'Plain text item',
  ]"
></c-two-column-list>
```

---

### `c-callout`
Highlighted message box for warnings, info, or notices.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `type` | Yes | `default`, `warning`, or `danger` |
| `title` | No | Bold title at top |
| `class` | No | Additional CSS classes |

**Slots**: Default - callout content

```html
<c-callout type="warning" title="Heads up!">
  Important information here.
</c-callout>
```

---

### `c-banner`
Large promotional card with image, text, and action buttons.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `size` | Yes | Tailwind fraction class (e.g., `basis-1/2`) |
| `eyebrow_text` | Yes | Small label above title |
| `title_text` | Yes | Main heading |
| `paragraph_text` | Yes | Description text |
| `buttons` | Yes | List of button dicts (see below) |
| `image_source` | Yes | Image URL |
| `image_alt` | Yes | Alt text for accessibility |

**Button dict structure**:
```python
{
  'style': 'btn-primary',  # or 'btn-outline'
  'name': 'Button text',
  'href': '/link',  # optional, for simple link
  'options': [  # optional, creates dropdown
    {'name': 'Option', 'href': '/url', 'icon': 'icon-name'}
  ]
}
```

**Slots**: None

```html
<c-banner
  size="basis-1/2"
  eyebrow_text="New Feature"
  title_text="Check This Out"
  paragraph_text="Description of the feature."
  :buttons="[{'style': 'btn-primary', 'name': 'Learn more', 'href': '/learn'}]"
  image_source="{% static 'png/image.png' %}"
  image_alt="Feature illustration"
></c-banner>
```

---

### `c-support-plea-banner`
Fixed-content banner encouraging donations/membership.

**Props**: None
**Slots**: None

```html
<c-support-plea-banner></c-support-plea-banner>
```

---

## Layout & Structure

### `c-expansion-panel`
Collapsible panel with expandable content. Uses AlpineJS Collapse plugin.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `title` | Yes | Panel header text |
| `class` | No | CSS classes |

**Slots**: Default - collapsible content

```html
<c-expansion-panel title="More details">
  Hidden content revealed on expand.
</c-expansion-panel>
```

---

### `c-tabs` + `c-tabs.tab`
Tabbed interface with responsive desktop tabs and mobile dropdown.

**`c-tabs` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `title` | Yes | Accessibility label for the tab group |
| `class` | No | CSS classes |

**`c-tabs.tab` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `name` | Yes | Tab label shown in selector |

**Slots**:
- `c-tabs`: Must contain `c-tabs.tab` elements
- `c-tabs.tab`: Panel content

**Features**: Keyboard navigation (arrows, Home, End)

```html
<c-tabs title="Options">
  <c-tabs.tab name="First">
    Content for first tab
  </c-tabs.tab>
  <c-tabs.tab name="Second">
    Content for second tab
  </c-tabs.tab>
</c-tabs>
```

---

### `c-data-table`
HTML table with header, body, and optional footer.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `columns` | Yes | Array of `{label, field}` dicts |
| `rows` | Yes | Array of dicts with keys matching column fields |
| `caption` | Yes | Accessibility caption (screen-reader only) |
| `align` | No | `left` (default), `center`, or `data-center` (first col left, rest centered) |
| `footer` | No | Array of footer row dicts (same structure as rows) |
| `safe` | No | Allows HTML in cells. **Warning**: XSS risk if used with user content |

**Slots**: None

```html
<c-data-table
  caption="User statistics"
  :columns="[
    {'label': 'Name', 'field': 'name'},
    {'label': 'Count', 'field': 'count'},
  ]"
  :rows="[
    {'name': 'Alice', 'count': '42'},
    {'name': 'Bob', 'count': '17'},
  ]"
></c-data-table>
```

---

### `c-dialog` + `c-dialog.trigger-button`
Modal dialog with overlay and trigger button.

**`c-dialog` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `dialog_class` | No | Classes for overlay container |
| `panel_class` | No | Classes for dialog panel |
| `class` | No | Additional classes |

**Slots**:
- `button_content`: Trigger button text
- `panel`: Modal content

**Features**: Esc to close, focus management. Use `x-on:click="close"` for close buttons.

```html
<c-dialog panel_class="p-5 banner max-w-70" dialog_class="items-center z-20">
  <c-slot name="button_content">Open Dialog</c-slot>
  <c-slot name="panel">
    Dialog content here.
    <button x-on:click="close" class="btn-outline">Close</button>
  </c-slot>
</c-dialog>
```

---

### `c-layout-with-navigation` + `c-layout-with-navigation.section`
Two-column layout with sidebar navigation and main content. Responsive (stacks on mobile). Auto-highlights active section on scroll.

**`c-layout-with-navigation` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `nav_items` | No | Navigation structure array (see below) |

**`c-layout-with-navigation.section` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `id` | Yes | Section identifier for nav highlighting |
| `class` | No | CSS classes |

**Nav item structure**:
```python
{'href': '#section-id', 'text': 'Section Name', 'children': [...]}
```

**Slots**: Both have default slots

**Important**: Only one layout per page. Sections should use the `c-layout-with-navigation.section` sub-component to enable scroll highlighting.

```html
<c-layout-with-navigation
  :nav_items="[
    {'href': '#intro', 'text': 'Introduction'},
    {'href': '#features', 'text': 'Features', 'children': [
      {'href': '#feature-1', 'text': 'Feature One'},
      {'href': '#feature-2', 'text': 'Feature Two'},
    ]},
  ]"
>
  <c-layout-with-navigation.section id="intro">
    <h2>Introduction</h2>
    <p>Content here...</p>
  </c-layout-with-navigation.section>

  <c-layout-with-navigation.section id="features">
    <h2>Features</h2>
    ...
  </c-layout-with-navigation.section>
</c-layout-with-navigation>
```

---

### `c-navigation-menu`
Standalone sidebar navigation. Desktop sticky sidebar + mobile dropdown. Highlights currently visible section on scroll.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `nav_items` | No | Array of nav items with `href`, `text`, and optional `children` |

**Slots**: None

**Note**: For scroll highlighting to work, target elements need `x-intersect="show"` directive.

```html
<c-navigation-menu
  :nav_items="[
    {'href': '#section-1', 'text': 'Section 1'},
    {'href': '#section-2', 'text': 'Section 2'},
  ]"
></c-navigation-menu>
```

---

### `c-menu-button` + `c-menu-button.item` + `c-menu-button.divider`
Dropdown menu with trigger button and menu items.

**`c-menu-button` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `button_class` | No | Classes for trigger button. Default: `btn-primary` |
| `menu_class` | No | Classes for menu dropdown |
| `position` | No | Dropdown position. Default: `bottom-start` |
| `widget_aria_label` | No | ARIA label for widget |
| `trigger_aria_label` | No | ARIA label for button |
| `menu_aria_label` | No | ARIA label for menu |

**`c-menu-button.item` Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `tag` | No | `a` (default) or `button` |
| `href` | No | Link destination |
| `disabled` | No | Disables item |
| `icon` | No | SVG icon name |
| `icon_class` | No | Icon styling |
| `item_class` | No | Item text styling |
| `li_class` | No | `<li>` styling |
| `aria_label` | No | Accessibility label |

**Slots**:
- `c-menu-button`: `button_content` and `menu_content`
- `c-menu-button.item`: Default slot for item text
- `c-menu-button.divider`: None (renders visual divider)

```html
<c-menu-button button_class="btn-outline">
  <c-slot name="button_content">Options</c-slot>
  <c-slot name="menu_content">
    <c-menu-button.item href="/edit" icon="pencil">Edit</c-menu-button.item>
    <c-menu-button.divider></c-menu-button.divider>
    <c-menu-button.item tag="button" icon="trash">Delete</c-menu-button.item>
  </c-slot>
</c-menu-button>
```

---

### `c-icon-link`
Styled link with icon and text. Icon appears in rounded circle with hover effects.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `icon` | Yes | SVG icon name |
| `href` | Yes | Link destination |
| (other HTML attrs) | No | Passed through to anchor |

**Slots**: Default - link text

```html
<c-icon-link icon="external-link" href="/external">
  View Source
</c-icon-link>
```

---

## Page Structure

### `c-header`
Site header with logo, search bar, and profile menu. Responsive.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `variant` | No | `homepage` for special styling, otherwise default |
| `request` | Yes | Django request object |
| `class` | No | CSS classes |

**Slots**: None

```html
<c-header request="{{ request }}"></c-header>
```

---

### `c-footer`
Site footer with donation banner, nav links, newsletter signup, and social icons.

**Props**: None
**Slots**: None

```html
<c-footer></c-footer>
```

---

## Search Components

Located in `cl/search/templates/cotton/corpus_search/`.

### `c-corpus-search`
Search form wrapper. Manages search state and form submission.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `class` | No | CSS classes |

**Slots**: Default - should contain search sub-components

---

### `c-corpus-search.scope`
Corpus selector (which database to search).

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `variant` | No | `menu` (default) or `tabs` |
| `verbose` | No | Show descriptions |
| `class`, `menu_class`, `item_class` | No | CSS classes |

---

### `c-corpus-search.input`
Search keyword input with operators modal showing Boolean syntax help.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `rounded` | No | Applies rounded styling |
| `class` | No | CSS classes |

**Slots**: Default - additional controls

---

### `c-corpus-search.button`
Search submit button.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `class` | No | CSS classes |

**Slots**: Default - button content

---

### `c-corpus-search.filters`
Advanced filter panel for search refinement.

---

### `c-corpus-search.date-selector`
Date range picker with relative date options (e.g., "Last 30 days").

---

### `c-corpus-search.mobile.dialog`
Mobile-optimized search interface in a dialog.

---

## Documentation Helpers

Used in the component library page (`/components/`). Useful for documenting new components.

### `c-library.list`
Container for documentation items.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `title` | Yes | Section title (e.g., "Props", "Slots") |

**Slots**: Default - contains `c-library.item` elements

---

### `c-library.item`
Individual documentation item.

**Props**:
| Prop | Required | Description |
|------|----------|-------------|
| `optional` | No | Marks item as optional |

**Slots**:
- `label`: Prop/slot name
- `description`: Documentation text

```html
<c-library.list title="Props">
  <c-library.item>
    <c-slot name="label"><code>title</code></c-slot>
    <c-slot name="description">The title text displayed.</c-slot>
  </c-library.item>
  <c-library.item optional>
    <c-slot name="label"><code>class</code></c-slot>
    <c-slot name="description">Optional CSS classes.</c-slot>
  </c-library.item>
</c-library.list>
```

---

## Notes for AI Agents

1. **Syntax**: Props with `:` prefix pass Python/JS expressions; without `:` pass strings
   - `:list="[...]"` - Python list
   - `title="My Title"` - string literal

2. **Slots**: Use `<c-slot name="...">` for named slots, or nest content directly for default slot

3. **Styling**: Components use Tailwind CSS. Common button classes: `btn-primary`, `btn-outline`

4. **Accessibility**:
   - Links should be underlined
   - Tables need captions
   - Interactive elements need ARIA labels
   - Dialogs handle focus management automatically

5. **Responsive**: Many components adapt to mobile automatically (tabs become dropdowns, layouts stack, etc.)

6. **Live component library**: View examples at `/components/` in the running app
