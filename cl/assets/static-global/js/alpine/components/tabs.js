const ACTIVE_TAB_CLASSES = 'bg-greyscale-100';
const INACTIVE_TAB_CLASSES = 'bg-greyscale-50';

document.addEventListener('alpine:init', () => {
  Alpine.data('tabsComponent', () => ({
    activeTab: '',
    tabs: [],
    registerTab() {
      this.tabs.push(this.$el.dataset?.tabId);
    },
    setActiveTab() {
      this.activeTab = this.$el.dataset?.tabId;
    },
    handleChange(event) {
      this.activeTab = event.target.value;
    },
    init() {
      this.$watch('tabs', (newVal) => (this.activeTab = newVal[0]));
    },
  }));
  Alpine.data('tabComponent', () => ({
    get isActive() {
      return this.$el.dataset?.tabId === this.activeTab;
    },

    get tabClass() {
      return this.isActive ? ACTIVE_TAB_CLASSES : INACTIVE_TAB_CLASSES;
    },
  }));
});
