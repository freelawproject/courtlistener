/**
 * SECURITY NOTE: This component assumes all navigation items are developer-defined
 * and not influenced by user input or external data sources. If this changes in the future
 * and navigation items become dynamic or user-influenced, proper URL encoding MUST be
 * implemented.
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('navMenu', () => ({
    menuOpen: false,
    buttonPressed: false,
    expandedSections: [],
    ids: ['listbox-option'],
    options: [],
    toggleMenu() {
      this.menuOpen = !this.menuOpen;
      this.buttonPressed = true;
    },
    closeMenu() {
      this.menuOpen = false;
    },
    toggleExpansion() {
      const index = this.expandedSections.findIndex((el) => el === this.target);
      if (index >= 0) {
        this.expandedSections.splice(index, 1);
      } else {
        this.expandedSections.push(this.target);
      }
    },
    get target() {
      return this.$el.dataset.intersectTarget;
    },
    get isExpanded() {
      return this.expandedSections.includes(this.target);
    },
    get visibleSectionText() {
      if (!this.buttonPressed) return 'On this page';
      const index = this.options.findIndex((opt) => opt.href === `#${this.$data.visibleSection}`);
      return index >= 0 ? this.options[index].text : '';
    },
    get iconClass() {
      return this.isExpanded ? 'transform rotate-180' : '';
    },
    get itemClass() {
      return this.isVisible ? 'text-primary-600' : '';
    },
    get hasVisibleChild() {
      const index = this.options.findIndex((el) => el.href === this.target);
      if (index === -1 || !this.options[index].children) return false;
      return this.options[index].children.some((child) => `#${this.visibleSection}` === child.href);
    },
    get markerClass() {
      return this.isVisible || this.hasVisibleChild ? '#B5362D' : '#E8E4DE';
    },
    get childClass() {
      return this.isVisible ? this.activeItemClasses : this.inactiveItemClasses;
    },
    get hasChildren() {
      const index = this.options.findIndex((el) => el.href === this.target);
      return index > -1 && this.options[index].children?.length > 0;
    },
    init() {
      this.options = JSON.parse(document.getElementById('nav-items').textContent);
      this.options.forEach((option) => {
        if (option.children) {
          this.expandedSections.push(option.href);
        }
      });
    },
  }));
});
