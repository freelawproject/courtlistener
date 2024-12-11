const defaultTheme = require('tailwindcss/defaultTheme');

/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */

module.exports = {
    content: [
        /**
         * HTML. Paths to Django template files that will contain Tailwind CSS classes.
         */

        /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
        '../templates/**/*.html',

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

        /**
         * JS: If you use Tailwind CSS in JavaScript, uncomment the following lines and make sure
         * patterns match your project structure.
         */
        /* JS 1: Ignore any JavaScript in node_modules folder. */
        // '!../../**/node_modules',
        /* JS 2: Process all JavaScript files in the project. */
        // '../../**/*.js',
        '../../**/templates/**/*.svg',
        '../../**/static-global/**/*.js',

        /**
         * Python: If you use Tailwind CSS classes in Python, uncomment the following line
         * and make sure the pattern below matches your project structure.
         */
        // '../../**/*.py'
    ],
    theme: {
      extend: {
        animation: {
          'fade-in': 'fadein 0.3s ease-in forwards',
          'fade-out': 'fadeout 0.2s ease-in forwards'
        },
        keyframes: {
          fadein: {
            '0%': { opacity: 0 },
            '100%': { opacity: 1 },
          },
          fadeout: {
            '0%': { opacity: 1 },
            '100%': { opacity: 0 , visibility: 'hidden'},
          },
        },
        fontFamily: {
          'sans': ['CooperHewitt', ...defaultTheme.fontFamily.sans],
        },
        colors: {
          'bcb-black': '#1A1A1A',
          // The yellow of the buttons is number 400!
          'saffron': {
            '50': '#fefaec',
            '100': '#fcf3c9',
            '200': '#f8e48f',
            '300': '#f5d154',
            '400': '#f3c33e',
            '500': '#eb9e15',
            '600': '#d0790f',
            '700': '#ad5610',
            '800': '#8c4314',
            '900': '#743713',
          },
        }
      }
    },
    plugins: [
        /**
         * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
         * for forms. If you don't like it or have own styling for forms,
         * comment the line below to disable '@tailwindcss/forms'.
         */
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/line-clamp'),
        require('@tailwindcss/aspect-ratio')
    ],
}
