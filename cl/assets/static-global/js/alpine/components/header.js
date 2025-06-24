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
    openProfileMenu() {
      this.profileMenuExpanded = true;
      const profileMenu = document.getElementById('header-profile-menu');
      this.$focus.within(profileMenu).first();
    },
    closeProfileMenu() {
      this.profileMenuExpanded = false;
      const triggerButton = document.getElementById('header-profile-trigger');
      this.$focus.focus(triggerButton);
    },
  }));
});
