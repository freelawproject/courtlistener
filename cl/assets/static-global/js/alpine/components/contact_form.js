document.addEventListener('alpine:init', () => {
  Alpine.data('contactForm', () => ({
    issueType: '',
    techTypes: [],
    get issue() {
      const isPartnershipsInquiry = this.issueType === 'partnerships';
      const isTechSupport = this.techTypes.includes(this.issueType);
      return {
        isPartnershipsInquiry: isPartnershipsInquiry,
        isNotPartnershipsInquiry: !isPartnershipsInquiry,
        isTechnicalSupport: isTechSupport,
        isNotTechnicalSupport: !isTechSupport,
        hasAdditionalFields: isPartnershipsInquiry || isTechSupport,
        requiresDocCheck: this.requiresCheckTypes.includes(this.issueType),
        noType: !this.issueType,
        isValidType: this.issueType && this.issueType !== 'legal',
      };
    },
    get messageLabel() {
      return this.issue.hasAdditionalFields ? 'Is there anything else we should know?' : 'Message';
    },
    get showHint() {
      return this.issue.noType ? this.$el.id === 'default' : this.issueType === this.$el.id;
    },
    onUpdateIssueType() {
      this.issueType = this.$el.value;
      if (!this.issue.hasAdditionalFields) this.$refs.message.setAttribute('required', '');
      else this.$refs.message.removeAttribute('required');
    },
    onUpdatePartnerBackground() {
      if (this.$el.checked && this.$el.value === 'other') this.$refs.otherBackground.focus();
    },
    checkOtherBackground() {
      const otherCheckbox = document.getElementById('id_partner_background').querySelectorAll('[value="other"]')[0];
      otherCheckbox.checked = true;
    },
    init() {
      // Fetch backend information: issue type options and Terms URL
      const issueTypeInput = this.$el.elements['issue_type'];
      if (issueTypeInput) this.issueType = issueTypeInput.value;
      this.requiresCheckTypes = JSON.parse(document.getElementById('requires-check-types').textContent);
      this.techTypes = JSON.parse(document.getElementById('tech-types').textContent);
    },
  }));
});
