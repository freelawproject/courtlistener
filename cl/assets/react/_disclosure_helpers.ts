import {GROSS_VALUE, INCOME_GAIN, VALUATION_METHODS} from "./_disclosure_models";

export const convertTD = (value, table, key) => {
  if (value == -1) {
    return ""
  }
  if (table == "Investments" && key == "transaction_value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Debts" && key == "value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Investments" && key == "income_during_reporting_period_code" && value) {
    return `${INCOME_GAIN[value]} (${value})`
  }
  if (table == "Investments" && key == "gross_value_method" && value) {
    return `${VALUATION_METHODS[value]} (${value})`
  }
  if (table == "Investments" && key == "gross_value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Investments" && key == "transaction_gain_code" && value) {
    return `${INCOME_GAIN[value]} (${value})`
  }

  return value
}

const getIndex = (value, arr) => {
    for(var i = 0; i < arr.length; i++) {
        if(arr[i] === value.toString()) {
            return i;
        }
    }
    return 0
}

export const fetch_year_index = (years, doc_ids) => {
  const search = window.location.search;
  const params = new URLSearchParams(search);
  var optional_doc_id = params.get('id');
  var index = 0;
  if (optional_doc_id != null ) {
    index = getIndex(optional_doc_id, doc_ids)
  }
  return [years[index], index]
}
