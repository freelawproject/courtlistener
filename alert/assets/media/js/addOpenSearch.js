function addOpenSearch()
{
  if ((typeof window.external == "object") && ((typeof window.external.AddSearchProvider == "unknown") || (typeof window.external.AddSearchProvider == "function"))) {
      window.external.AddSearchProvider("http://courtlistener.com/media/xml/opensearch.xml");
  } else {
    alert("You will need a browser which supports OpenSearch to install this plugin.");
  }
}

