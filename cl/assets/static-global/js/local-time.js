// Rewrites each <time class="local-time" datetime="..."> in the visitor's own
// time zone, with the zone's abbreviation. The server renders the same time in
// the site's time zone as a fallback, which stays in place if this fails.
document.querySelectorAll("time.local-time[datetime]").forEach((element) => {
  const date = new Date(element.getAttribute("datetime"));
  if (Number.isNaN(date.getTime())) {
    return;
  }
  element.textContent = date.toLocaleString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
});
