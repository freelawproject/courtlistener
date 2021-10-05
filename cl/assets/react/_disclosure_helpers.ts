import {GROSS_VALUE, INCOME_GAIN, VALUATION_METHODS} from "./_disclosure_models";

export const convertTD = (value, table, key) => {
  if (value == -1 || !value) {
    return ""
  }
  if (["Investments", "Debts"].indexOf(table) == -1) {
    return value
  }
  if (["transaction_value_code", "value_code", "gross_value_code"].indexOf(key) > -1) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (["income_during_reporting_period_code", "transaction_gain_code"].indexOf(key) > -1) {
    return `${INCOME_GAIN[value]} (${value})`
  }
  if (key == "gross_value_method" && value) {
    return `${VALUATION_METHODS[value]} (${value})`
  }
  return value
}

const getIndex = (value, arr) => {
    // Sadly we need this method to check the index of an item in a list
    // This helps us select the correct tab on page load
    for(var i = 0; i < arr.length; i++) {
        if(arr[i] === value.toString()) {
            return i;
        }
    }
    return 0
}

export const fetch_year_index = (years, doc_ids) => {
  // Given a list of years, doc-ids identify the index of the year
  // to select in the tab array of years
  //Fetch year index is not pretty.
  const search = window.location.search;
  const params = new URLSearchParams(search);
  var optional_doc_id = params.get('id');
  var index = 0;
  if (optional_doc_id != null ) {
    index = getIndex(optional_doc_id, doc_ids)
  }
  return [years[index], index]
}
