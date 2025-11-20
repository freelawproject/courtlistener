document.addEventListener('alpine:init', () => {
  Alpine.data('expansionPanel', () => ({
    isExpanded: false,
    get supportCaretClass() {
      return this.isExpanded ? 'transform rotate-180' : '';
    },
    get iconClass() {
      return this.isExpanded ? 'transform rotate-180' : '';
    },
    toggleExpansion() {
      this.isExpanded = !this.isExpanded;
    },
  }));
});
