// Variables
var relatedCloseAll = 'feedbackRelatedCloseAll';

// Utils
var entityMap = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
  '/': '&#x2F;',
  '`': '&#x60;',
  '=': '&#x3D;'
};

function escapeHtml (string) {
  return String(string).replace(/[&<>"'`=\/]/g, function (s) {
    return entityMap[s];
  });
}

function getCookie(cname) {
  var name = cname + "=";
  var decodedCookie = decodeURIComponent(document.cookie);
  var ca = decodedCookie.split(';');
  for(var i = 0; i <ca.length; i++) {
    var c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  return "";
}

function hasCookie(name) {
  return document.cookie.split(';').some(function (item) {
    return item.trim().indexOf(name + '=') === 0
  });
}

function setCookie(name, value, maxAge) {
  document.cookie = name + '=' + value + ';path=/;max-age=' + maxAge;
}

// Actual methods
function clickRelated(algorithm, seedId, targetId, rank, seedTitle) {
  setCookie('clickFromRelated' + targetId + '_id', seedId, 3600);
  setCookie('clickFromRelated' + targetId + '_title', seedTitle, 3600);

  // Send to Matomo
  var _paq = window._paq || [];
  _paq.push(['trackEvent', 'clickRelated', 'clickRelated_' + algorithm + '_seed_' + seedId, targetId, rank]);
}

function getFeedbackName(seedId, targetId) {
  return 'feedbackRelated_' + seedId + '_' + targetId;
}

function submitRelatedFeedback(button, seedId, targetId, feedback) {
  feedback = String(feedback);

  // Send to Matomo
  var _paq = window._paq || [];
  _paq.push(['trackEvent', 'feedbackRelated', getFeedbackName(seedId, targetId), feedback]);

  // Set cookie
  // document.cookie =  + '=' + feedback + ';path=/;max-age=31536000'; // 1 year
  setCookie(getFeedbackName(seedId, targetId), feedback, 31536000); // 1 year

  $(button).parent().fadeOut();
}

function closeRelatedFeedback(button, seedId, targetId) {
  // Unset with: setCookie(relatedCloseAll, 1, 0);

  // Send to Matomo
  var _paq = window._paq || [];
  _paq.push(['trackEvent', 'feedbackRelatedClose', getFeedbackName(seedId, targetId)]);

  // Set cookie
  document.cookie = getFeedbackName(seedId, targetId) + '=close;path=/;max-age=315360000'; // 10 years
  document.cookie = relatedCloseAll + '=1;path=/;max-age=2678400'; // 1 month

  $(button).parent().fadeOut();
}

function insertFeedbackForm(targetId, ratio) {
  // How many random users should see this form? (default: 5%)
  ratio = typeof ratio !== 'undefined' ? ratio : 0.05;

  // Cookies must exists and random test must be true
  if (Math.random() < ratio && hasCookie('clickFromRelated' + targetId + '_id') && hasCookie('clickFromRelated' + targetId + '_title')  ) {

    var seedId = parseInt(getCookie('clickFromRelated' + targetId + '_id'));
    var seedTitle = escapeHtml(getCookie('clickFromRelated' + targetId + '_title'));

    if (!isNaN(seedId)) {
      if (!hasCookie(relatedCloseAll) && !hasCookie(getFeedbackName(seedId, targetId))) {

        var feedbackForm = '<div class="alert alert-info alert-dismissible" role="alert">';
        feedbackForm += '<button type="button" class="close" onclick="closeRelatedFeedback(this, ' + seedId + ', ' + targetId + ');" aria-label="Close"><span aria-hidden="true">&times;</span></button>';
        feedbackForm += 'Was this case a good recommendation for <u>' + seedTitle +'</u>? ';
        feedbackForm += '<button class="btn btn-xs btn-default" onclick="submitRelatedFeedback(this, ' + seedId + ', ' + targetId + ', 1);"><i class="fa fa-thumbs-up"></i> Yes</button>&nbsp;';
        feedbackForm += '<button class="btn btn-xs btn-default" onclick="submitRelatedFeedback(this, ' + seedId + ', ' + targetId + ', 0);"><i class="fa fa-thumbs-down"></i> No</button></div>';

        $('article').prepend(feedbackForm);
      }
    }
  }
}
