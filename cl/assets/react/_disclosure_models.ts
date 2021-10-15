export const INCOME_GAIN = {
  A: '1‑1,000',
  B: '1,001‑2,500',
  C: '2,501‑5,000',
  D: '5,001‑15,000',
  E: '15,001‑50,000',
  F: '50,001‑100,000',
  G: '100,001‑1,000,000',
  H1: '1,000,001‑5,000,000',
  H2: '5,000,001+',
  '-1': 'Failed Extraction',
};

export const GROSS_VALUE = {
  J: '1‑15,000',
  K: '15,001‑50,000',
  L: '50,001‑100,000',
  M: '100,001‑250,000',
  N: '250,001‑500,000',
  O: '500,001‑1,000,000',
  P1: '1,000,001‑5,000,000',
  P2: '5,000,001‑25,000,000',
  P3: '25,000,001‑50,000,000',
  P4: '50,000,00+',
  '-1': 'Failed Extraction',
};

export const VALUATION_METHODS = {
  Q: 'Appraisal',
  R: 'Cost (Real Estate Only)',
  S: 'Assessment',
  T: 'Cash Market',
  U: 'Book Value',
  V: 'Other',
  W: 'Estimated',
  '-1': 'Failed Extraction',
};

const investmentFields = {
  Description: 'description',
  'Gross Val. Code': 'gross_value_code',
  'Gross Val. Method': 'gross_value_method',
  'Income Code': 'income_during_reporting_period_code',
  'Income Type': 'income_during_reporting_period_type',
  'Trans. Type': 'transaction_during_reporting_period',
  'Trans. Date': 'transaction_date_raw',
  'Trans. Value': 'transaction_value_code',
  'Trans. Gain': 'transaction_gain_code',
  'Trans. Partner': 'transaction_partner',
};
const giftFields = {
  Source: 'source',
  Value: 'value',
  Description: 'description',
};
const reimbursementsFields = {
  Dates: 'date_raw',
  Location: 'location',
  Source: 'source',
  Purpose: 'purpose',
  Items: 'items_paid_or_provided',
};
const noninvestmentFields = {
  Dates: 'date_raw',
  Source: 'source_type',
  'Income Amount': 'income_amount',
};
const agreementFields = {
  Dates: 'date_raw',
  Source: 'parties_and_terms',
  'Parties and Terms': 'parties_and_terms',
};
const positionFields = {
  Position: 'position',
  Organization: 'organization_name',
};
const debtFields = {
  'Creditor Name': 'creditor_name',
  Description: 'description',
  'Value Code': 'value_code',
};
const spouseFields = {
  Date: 'date_raw',
  "Source": 'source_type',
};

export const disclosureModel = {
  investments: {
    fields: investmentFields,
    title: 'Investments',
    api: 'investments',
    admin_key: 'investment',
  },
  gifts: {
    fields: giftFields,
    title: 'Gifts',
    api: 'gifts',
    admin_key: 'gift',
  },
  debts: {
    fields: debtFields,
    title: 'Debts',
    api: 'debts',
    admin_key: 'debt',
  },
  positions: {
    fields: positionFields,
    title: 'Positions',
    api: 'disclosure-positions',
    admin_key: 'position',
  },
  spouse_incomes: {
    fields: spouseFields,
    title: 'Spousal Income',
    api: 'spouse-incomes',
    admin_key: 'spouse-income',
  },
  agreements: {
    fields: agreementFields,
    title: 'Agreements',
    api: 'agreements',
    admin_key: 'agreement',
  },
  non_investment_incomes: {
    fields: noninvestmentFields,
    title: 'Non Investment Income',
    api: 'non-investment-incomes',
    admin_key: 'non-investment-income',
  },
  reimbursements: {
    fields: reimbursementsFields,
    title: 'Reimbursements',
    api: 'reimbursements',
    admin_key: 'reimbursement',
  },
};
