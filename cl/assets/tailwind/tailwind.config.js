module.exports = {
  content: {
    relative: true,
    files: [
      /**
       * HTML. Paths to Django template files that will contain Tailwind CSS classes.
       */

      /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
      '../templates/**/*.html',

      /*
       * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
       * Adjust the following line to match your project structure.
       */
      '../../**/templates/**/*.html',

      /*  Alpine components that could contain Tailwind CSS classes. */
      '../static-global/js/alpine/components/*.js',

      /*  SVG files that could contain Tailwind CSS classes. */
      '../static-global/svg/*.svg',
    ],
  },
  theme: {
    extend: {
      screens: {
        xs: '392px',
      },
      spacing: {
        4.5: '1.125rem', // 18px
        7.5: '1.875rem', // 30px
        13: '3.25rem', // 52px
        15: '3.75rem', // 60px
        18: '4.5rem', // 72px
        35: '8.75rem', // 140px
        41: '10.25rem', // 164px
        42: '10.5rem', // 168px
        53: '13.25rem', // 212px
        70: '17.5rem', // 280px
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        cooper: ['Cooper Hewitt', 'sans-serif'],
        mono: ['DM Mono', 'mono'],
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
          100: '#F4EBFF',
          300: '#D6BBFB',
          600: '#7F56D9',
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
      fontSize: {
        xs: ['12px', '18px'],
        'xs-cooper': ['12px', '18px'],
        sm: ['14px', '20px'],
        md: ['16px', '24px'],
        lg: ['18px', '28px'],
        'lg-cooper': ['18px', '26px'],
        xl: ['20px', '28px'],
        'display-xs': ['24px', '32px'],
        'display-sm': ['30px', '38px'],
        'display-sm-cooper': ['28px', '44px'],
        'display-md': ['32px', '40px'],
        'display-lg': ['40px', '48px'],
        'display-xl': ['44px', '52px'],
      },
      maxWidth: {
        content: '948px',
      },
    },
  },
  plugins: [],
};
