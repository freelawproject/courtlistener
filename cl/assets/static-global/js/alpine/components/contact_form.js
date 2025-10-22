document.addEventListener('alpine:init', () => {
  Alpine.data('contactForm', () => ({
    issueType: '',
    techTypes: [],
    termsURL: '',
    get issue() {
      const isPartnershipsInquiry = this.issueType === 'partnerships';
      const isTechSupport = this.techTypes.includes(this.issueType);
      return {
        isPartnershipsInquiry: isPartnershipsInquiry,
        isNotPartnershipsInquiry: !isPartnershipsInquiry,
        isTechnicalSupport: isTechSupport,
        isNotTechnicalSupport: !isTechSupport,
        hasAdditionalFields: isPartnershipsInquiry || isTechSupport,
        noType: !this.issueType,
        isValidType: this.issueType && this.issueType !== 'legal',
      };
    },
    get messageLabel() {
      return this.issue.hasAdditionalFields ? 'Is there anything else we should know?' : 'Message';
    },
    get hint() {
      const discussionsLink =
        'For community help and to see what others are discussing, visit the <a href="https://github.com/freelawproject/courtlistener/discussions">CourtListener Discussion</a> forum.';
      const hints = {
        support: `Need a hand with CourtListener? First, check the other options above to make sure your question gets to the right team. Then, tell us what you’re trying to do and include the exact page link(s).<br><br>${discussionsLink}`,
        api: `<a href="https://free.law">Free Law Project</a> makes it possible for you and your team to access our data. ${discussionsLink}`,
        recap:
          'Having trouble with the <a href="https://free.law/recap">RECAP extension</a>? Include your browser and version, the page/court link you were on, what you expected, and what happened instead.',
        partnerships:
          'We collaborate with organizations on licensing, integrations, and API partnerships. Learn more <a href="https://free.law/about/">about us</a> and how we work with <a href="https://free.law/startups/">startups</a>.',
        legal:
          '<strong>We do not provide legal help</strong>. You may wish to contact a qualified attorney, reach out to your local bar association to see if they operate a lawyer referral service, or try <a href="https://www.justia.com/lawyers">Justia\'s lawyer directory</a>. Additionally, many counties and law schools operate law libraries open to the general public, where you can conduct general legal research.',
        removal: `<strong>If you want something taken off of our website</strong>, please see our <a href="${this.termsURL}">removal policy</a> for how to proceed. You <em>must</em> provide a link of the item you need reviewed.`,
      };
      return this.issue.noType ? 'Please select an option above to get started.' : hints[this.issueType] ?? '';
    },
    onUpdate() {
      this.issueType = this.$el.value;
      if (!this.issue.hasAdditionalFields) this.$refs.message.setAttribute('required', '');
      else this.$refs.message.removeAttribute('required');
    },
    init() {
      // Fetch backend information: issue type options and Terms URL
      const issueTypeInput = this.$el.elements['issue_type'];
      if (issueTypeInput) this.issueType = issueTypeInput.value;
      this.techTypes = JSON.parse(document.getElementById('tech-types').textContent);
      this.termsURL = JSON.parse(document.getElementById('terms-url').textContent);
    },
  }));
});
