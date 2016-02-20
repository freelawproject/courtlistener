function addOpenSearch()
{
  if ((typeof window.external == "object") && ((typeof window.external.AddSearchProvider == "undefined") || (typeof window.external.AddSearchProvider == "function"))) {
      window.external.AddSearchProvider("https://www.courtlistener.com/media/xml/opensearch.xml");
  } else {
    alert("You will need a browser which supports OpenSearch to install this plugin.");
  }
}
