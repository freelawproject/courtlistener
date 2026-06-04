const createUtils = () => ({
  onBreakpointChange(callback) {
    const mobileBreakpoint = getComputedStyle(document.documentElement)
      .getPropertyValue('--mobile-breakpoint')
      .trim();
    const mediaQuery = window.matchMedia(`(min-width: ${mobileBreakpoint})`);
    mediaQuery.addEventListener('change', callback);
  },
});

document.addEventListener('alpine:init', () => {
  Alpine.data('utils', createUtils);
});
