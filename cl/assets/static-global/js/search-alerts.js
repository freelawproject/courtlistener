document.addEventListener('DOMContentLoaded', function () {
  const rateSelect = document.getElementById('id_rate');
  const quotaWarning = document.getElementById('quota-warning');
  const saveBtn = document.getElementById('alertSave');
  const alertType = alertsContext.alertType;
  const FreeRTMsg = document.getElementById('msg-rt-free');
  const FreeQuotaMsg = document.getElementById('msg-quota-free');
  const MemberQuotaMsg = document.getElementById('msg-quota-member');

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
    const isMember = alertsContext.level !== 'free';
    const rateGroup = rateValue === 'rt' ? 'rt' : 'other_rates';
    const used = alertsContext.counts[rateGroup] || 0;
    const allowed =
      alertsContext.limits[rateGroup][userLevel] != null
        ? alertsContext.limits[rateGroup][userLevel]
        : alertsContext.limits[rateGroup]['free'];

    quotaWarning.classList.add('hidden');
    FreeQuotaMsg.classList.add('hidden');
    MemberQuotaMsg.classList.add('hidden');
    FreeRTMsg.classList.add('hidden');
    saveBtn.disabled = false;
    if (rateValue === 'rt' && !isMember) {
      // Display the custom RT alert message for free users.
      quotaWarning.classList.remove('hidden');
      FreeRTMsg.classList.remove('hidden');
      saveBtn.disabled = true;
      return;
    }

    if (used >= allowed && !editAlert) {
      if (isMember) {
        // Member has reached the quota for this rate group.
        MemberQuotaMsg.classList.remove('hidden');
      } else {
        // Free user has reached their quota for other rates.
        FreeQuotaMsg.classList.remove('hidden');
      }
      // Show the limit warning if the quota has been reached and the user is not editing their alerts.
      quotaWarning.classList.remove('hidden');
      saveBtn.disabled = true;
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
