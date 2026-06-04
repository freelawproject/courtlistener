# Third-Party CSS

This directory contains stylesheets for third-party libraries used in new templates.

- All files are **upstream code** and must **not be edited directly**.
- If the stylesheet is widely used and needs to be available globally, import it in Tailwind's input file. This ensures the code is minified.
- If the stylesheet is **not** used across all pages:
  - Make sure you include both non-minified and minified versions in this directory.
  - Import the stylesheet only in the templates that require it.
  - Inside a `head` block, use conditional `<link>` tags to import the non-minified version when `DEBUG=True`, and the minified version otherwise.
- To override styles, use the appropriate layer in Tailwind's `input.css` file.

Refer to our [New Frontend Architecture][wiki] wiki for further reference.

[wiki]: https://github.com/freelawproject/courtlistener/wiki/New-Frontend-Architecture
