document.addEventListener('alpine:init', () => {
  Alpine.data('expansionPanel', () => ({
    isExpanded: false,
    get iconClass() {
      return this.isExpanded ? 'transform rotate-180' : '';
    },
    toggleExpansion() {
      this.isExpanded = !this.isExpanded;
    },
    get dropdownButtonIdGroup() {
      return ['dropdown-button-menu'];
    },
    get dropdownButtonMenuId() {
      return this.$id('dropdown-button-menu');
    },
  }));
});
