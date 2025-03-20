module.exports = {
  content: [
    /**
     * HTML. Paths to Django template files that will contain Tailwind CSS classes.
     */

    /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
    '../templates/**/*.html',

    /*
     * Custom fonts
     */
    '../../assets/static-global/fonts/**/*.woff',
    '../../assets/static-global/fonts/**/*.woff2',

    /*
     * Main templates directory of the project (BASE_DIR/templates).
     * Adjust the following line to match your project structure.
     */
    '../../templates/**/*.html',

    /*
     * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
     * Adjust the following line to match your project structure.
     */
    '../../**/templates/**/*.html',
    '../../**/templates/**/*.svg',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        cooper: ['Cooper Hewitt', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
