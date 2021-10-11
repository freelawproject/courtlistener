import { GROSS_VALUE, INCOME_GAIN, VALUATION_METHODS } from './_disclosure_models';

export const convertTD = (value, table, key) => {
  if (value == -1 || !value) {
    return '';
  }
  if (['Investments', 'Debts'].indexOf(table) == -1) {
    return value;
  }
  if (['transaction_value_code', 'value_code', 'gross_value_code'].indexOf(key) > -1) {
    return `${GROSS_VALUE[value]} (${value})`;
  }
  if (['income_during_reporting_period_code', 'transaction_gain_code'].indexOf(key) > -1) {
    return `${INCOME_GAIN[value]} (${value})`;
  }
  if (key == 'gross_value_method' && value) {
    return `${VALUATION_METHODS[value]} (${value})`;
  }
  return value;
};
