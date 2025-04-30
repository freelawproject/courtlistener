/*
To use this component, add this to your template right after `{% extends "new_base.html" %}`

{% load component_tags %}
{% require_script "js/alpine/components/intersect.js" %}
{% require_script "js/alpine/plugins/intersect@3.14.8" defer=True %}

Note we need to also register the Alpine plugin intersect for this to work.
*/

document.addEventListener('alpine:init', () => {
  Alpine.data('intersect', () => ({
    visibleSection: '', // id of the last intersected element
    activeItemClasses: '',
    inactiveItemClasses: '',
    intersectIdAttr: '', // camelCase name of the attribute used to associate $el with target
    show() {
      this.visibleSection = this.$el.id;
    },
    get isVisible() {
      return `#${this.visibleSection}` === this.$el.dataset[this.intersectIdAttr];
    },
    init() {
      this.activeItemClasses = this.$el.dataset?.activeItemClasses;
      this.inactiveItemClasses = this.$el.dataset?.inactiveItemClasses;
      this.intersectIdAttr = this.$el.dataset?.intersectIdAttr;
      this.$nextTick(() => {
        this.visibleSection = this.$el.dataset?.firstActive ?? '';
      });
    },
  }));
});
