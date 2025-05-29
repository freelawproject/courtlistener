document.addEventListener('DOMContentLoaded', function () {
  const rateSelect = document.getElementById('id_rate');
  const quotaWarning = document.getElementById('quota-warning');
  const saveBtn = document.getElementById('alertSave');
  const limitMsg = quotaWarning.querySelector('.limit-message');
  const alertType = alertsContext.alertType;

  // Opinions and OA alerts limits logic
  function otherAlerts() {
    const val = rateSelect.value;
    if (val === 'rt' && !isMember) {
      quotaWarning.classList.remove('hidden');
      saveBtn.disabled = true;
    } else {
      quotaWarning.classList.add('hidden');
      saveBtn.disabled = false;
    }
  }

  // RECAP Search alerts limits logic
  function recapAlerts() {
    const rateValue = rateSelect.value;
    const userLevel = alertsContext.level;
    const editAlert = alertsContext.editAlert;
    const membership = alertsContext.names[userLevel] || 'Free';
    const rateGroup = rateValue === 'rt' ? 'rt' : 'other_rates';
    const rateLabel = rateValue === 'rt' ? 'Real Time' : 'Daily, Weekly or Monthly';
    const used = alertsContext.counts[rateGroup] || 0;
    const allowed =
      alertsContext.limits[rateGroup][userLevel] != null
        ? alertsContext.limits[rateGroup][userLevel]
        : alertsContext.limits[rateGroup]['free'];

    if (rateValue === 'rt' && membership === 'Free') {
      limitMsg.textContent = 'You must be a member to create Real Time alerts.';
      quotaWarning.classList.remove('hidden');
      saveBtn.disabled = true;
      return;
    }

    if (used >= allowed && !editAlert) {
      // Show the limit warning if the quota has been reached and the user is not editing their alerts.
      limitMsg.textContent = `Your ${membership} membership allows only ${allowed} "${rateLabel}" alerts; you already have ${used}.`;
      quotaWarning.classList.remove('hidden');
      saveBtn.disabled = true;
    } else {
      quotaWarning.classList.add('hidden');
      saveBtn.disabled = false;
    }
  }

  function handleQuotaCheck() {
    if (alertType === 'r') {
      recapAlerts();
    } else {
      otherAlerts();
    }
  }

  handleQuotaCheck();
  rateSelect.addEventListener('change', handleQuotaCheck);
});
