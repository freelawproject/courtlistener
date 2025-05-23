document.addEventListener('alpine:init', () => {
  Alpine.data('expansionPanel', () => ({
    isExpanded: false,
    get iconClass() {
      return this.isExpanded ? 'transform rotate-180' : '';
    },
    toggleExpansion() {
      this.isExpanded = !this.isExpanded;
    },
  }));
});
