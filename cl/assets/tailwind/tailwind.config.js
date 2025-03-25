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
    '../../**/templates/**/*.svg',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        cooper: ['Cooper Hewitt', 'sans-serif'],
      },
      colors: {
        greyscale: {
          25: '#FDFCFB',
          50: '#FBFAF8',
          100: '#F5F3EF',
          200: '#E8E4DE',
          300: '#D6D0C6',
          400: '#A8A091',
          500: '#776F61',
          600: '#574F40',
          700: '#453F35',
          800: '#29261F',
          900: '#1C1814',
          950: '#171411',
        },
        primary: {
          25: '#FDF9F7',
          50: '#FBF4EF',
          100: '#F7E6DE',
          200: '#EFCBBD',
          300: '#E19684',
          400: '#D56958',
          500: '#CD4137',
          600: '#B5362D',
          700: '#9B2E27',
          800: '#832720',
          900: '#6A201A',
          950: '#4E1713',
        },
        brand: {
          300: '#D6BBFB',
          700: '#6941C6',
        },
        yellow: {
          50: '#FFFAEB',
          400: '#FDB022',
        },
        blue: {
          700: '#004EEB',
        },
        red: {
          400: '#FF692E',
          500: '#E62E05',
        },
      },
    },
  },
  plugins: [],
};
