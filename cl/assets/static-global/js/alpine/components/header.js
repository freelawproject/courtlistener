document.addEventListener('alpine:init', () => {
  Alpine.data('header', () => ({
    profileMenuExpanded: false,
    supportMenuExpanded: false,
    get profileCaretClass() {
      return this.profileMenuExpanded ? 'transform rotate-180' : '';
    },
    get supportCaretClass() {
      return this.supportMenuExpanded ? 'transform rotate-180' : '';
    },
    toggleSupportMenu() {
      this.supportMenuExpanded = !this.supportMenuExpanded;
    },
    closeSupportMenu() {
      this.supportMenuExpanded = false;
    },
    toggleProfileMenu() {
      this.profileMenuExpanded = !this.profileMenuExpanded;
    },
    closeProfileMenu() {
      this.profileMenuExpanded = false;
    },
  }));
});
