from datetime import date

from cl.search.models import Court

# IDB data sources
CV_OLD = 1
CV_2017 = 2
CR_OLD = 3
CR_2017 = 4
APP_OLD = 5
APP_2017 = 6
BANKR_2017 = 7
DATASET_SOURCES = (
    (CV_OLD, 'Civil cases filed and terminated from SY 1970 through SY '
             '1987'),
    (CV_2017, 'Civil cases filed, terminated, and pending from SY 1988 '
              'to present (2017)'),
    (CR_OLD, 'Criminal defendants filed and terminated from SY 1970 '
             'through FY 1995'),
    (CR_2017, 'Criminal defendants filed, terminated, and pending from '
              'FY 1996 to present (2017)'),
    (APP_OLD, 'Appellate cases filed and terminated from SY 1971 '
              'through FY 2007'),
    (APP_2017, 'Appellate cases filed, terminated, and pending from FY '
               '2008 to present (2017)'),
    (BANKR_2017, 'Bankruptcy cases filed, terminated, and pending from '
                 'FY 2008 to present (2017)'),
)

# All of the field information for the IDB fields:
#   key name (e.g. 'CIRCUIT'): The name of the column in the IDB.
#   'sources': The IDB datasets that use this field.
#   'field': The name of the field in the FjcIntegratedDatabase model.
#   'type': The type of data in the field.
IDB_FIELD_DATA = {
    # Shared
    'CIRCUIT': {
        'sources': [CV_2017, CR_2017],
        'field': 'circuit',
        'type': Court,
    },
    'DISTRICT': {
        'sources': [CV_2017, CR_2017],
        'field': 'district',
        'type': Court,
    },
    'OFFICE': {
        'sources': [CV_2017, CR_2017],
        'field': 'office',
        'type': str,
    },
    'DOCKET': {
        'sources': [CV_2017, CR_2017],
        'field': 'docket_number',
        'type': str,
    },
    'ORIGIN': {
        'sources': [CV_2017],
        'field': 'origin',
        'type': int,
    },
    'FILEDATE': {
        'sources': [CV_2017, CR_2017],
        'field': 'date_filed',
        'type': date,
    },
    'COUNTY': {
        'sources': [CV_2017, CR_2017],
        'field': 'county_of_residence',
        'type': int,
    },
    'TERMDATE': {
        'sources': [CV_2017, CR_2017],
        'field': 'date_terminated',
        'type': date,
    },
    'TAPEYEAR': {
        'sources': [CV_2017, CR_2017],
        'field': 'year_of_tape',
        'type': int,
    },

    # Civil only
    'JURIS': {
        'sources': [CV_2017],
        'field': 'jurisdiction',
        'type': int,
    },
    'NOS': {
        'sources': [CV_2017],
        'field': 'nature_of_suit',
        'type': int,
    },
    'TITL': {
        'sources': [CV_2017],
        'field': 'title',
        'type': str,
    },
    'SECTION': {
        'sources': [CV_2017],
        'field': 'section',
        'type': str,
    },
    'SUBSECTION': {
        'sources': [CV_2017],
        'field': 'subsection',
        'type': str,
    },
    'RESIDENC': {
        'sources': [CV_2017],
        'field': 'diversity_of_residence',
        'type': int,
    },
    'CLASSACT': {
        'sources': [CV_2017],
        'field': 'class_action',
        'type': bool
    },
    'DEMANDED': {
        'sources': [CV_2017],
        'field': 'monetary_demand',
        'type': int,
    },
    'ARBIT': {
        'sources': [CV_2017],
        'field': 'arbitration_at_filing',
        'type': str,
    },
    'MDLDOCK': {
        'sources': [CV_2017],
        'field': 'multidistrict_litigation_docket_number',
        'type': str,
    },
    'PLT': {
        'sources': [CV_2017],
        'field': 'plaintiff',
        'type': str,
    },
    'DEF': {
        'sources': [CV_2017],
        'field': 'defendant',
        'type': str,
    },
    'TRANSOFF': {
        'sources': [CV_2017],
        'field': 'transfer_office',
        'type': str,
    },
    'TRANSDAT': {
        'sources': [CV_2017],
        'field': 'date_transfer',
        'type': date,
    },
    'TRANSDOC': {
        'sources': [CV_2017],
        'field': 'transfer_docket_number',
        'type': str,
    },
    'TRANSORG': {
        'sources': [CV_2017],
        'field': 'transfer_origin',
        'type': str,
    },
    'TRCLACT': {
        'sources': [CV_2017],
        'field': 'termination_class_action_status',
        'type': int,
    },
    'PROCPROG': {
        'sources': [CV_2017],
        'field': 'procedural_progress',
        'type': int,
    },
    'DISP': {
        'sources': [CV_2017],
        'field': 'disposition',
        'type': int,
    },
    'NOJ': {
        'sources': [CV_2017],
        'field': 'nature_of_judgement',
        'type': int,
    },
    'AMTREC': {
        'sources': [CV_2017],
        'field': 'amount_received',
        'type': int,
    },
    'JUDGMENT': {
        'sources': [CV_2017],
        'field': 'judgment',
        'type': int,
    },
    'PROSE': {
        'sources': [CV_2017],
        'field': 'pro_se',
        'type': int,
    },

    # Criminal only
    'D2FOFFCD1': {
        'sources': [CR_2017],
        'field': 'nature_of_offense',
        'type': str,
    },
    'VER': {
        'sources': [CR_2017],
        'field': 'version',
        'type': int,
    },
    'TRANOFF': {
        'sources': [CR_2017],
        'field': 'transfer_office',
        'type': str,
    },
    'TRANDOCK': {
        'sources': [CR_2017],
        'field': 'transfer_docket_number',
        'type': str,
    },
    'MAGDOCK': {
        'sources': [CR_2017],
        'field': 'multidistrict_litigation_docket_number',
        'type': str,
    },
}


INSURANCE = 110
MARINE_CONTRACT = 120
MILLER_ACT = 130
NEGOTIABLE_INSTRUMENTS = 140
OVERPAYMENTS_AND_ENFORCEMENTS = 150
OVERPAYMENTS_MEDICARE = 151
RECOVERY_OF_STUDENT_LOANS = 152
RECOVERY_OF_VET_BENEFITS_OVERPAYMENTS = 153
STOCKHOLDER_SUITS = 160
CONTRACT_OTHER = 190
CONTRACT_PRODUCT_LIABILITY = 195
CONTRACT_FRANCHISE = 196
LAND_CONDEMNATION = 210
FORECLOSURE = 220
RENT_LEASE_EJECTMENT = 230
TORT_LAND = 245
TORT_PRODUCT_LIABILITY = 245
REAL_PROPERTY_ACTIONS_OTHER = 290
AIRPLANE_PERSONAL_INJURY = 310
AIRPLANE_PRODUCT_LIABILITY = 315
ASSAULT_LIBEL_AND_SLANDER = 320
FEDERAL_EMPLOYERS_LIABILITY = 330
MARINE_PERSONAL_INJURY = 340
MARINE_PRODUCT_LIABILITY = 345
MOTOR_VEHICLE_PERSONAL_INJURY = 350
MOTOR_VEHICLE_PRODUCT_LIABILITY = 355
PERSONAL_INJURY_OTHER = 360
MEDICAL_MALPRACTICE = 362
PERSONAL_INJURY_PRODUCT_LIABILITY = 365
HEALTH_CARE_PHARM = 367
ASBESTOS_PERSONAL_INJURY = 368
FRAUD_OTHER = 370
TRUTH_IN_LENDING = 371
FALSE_CLAIMS_ACT = 375
PERSONAL_PROPERTY_DAMAGE_OTHER = 380
PROPERTY_DAMAGE_PRODUCT_LIABILITY = 385
STATE_RE_APPORTIONMENT = 400
ANTITRUST = 410
BANKRUPTCY_APPEALS = 422
BANKRUPTCY_WITHDRAWAL = 423
BANKS_AND_BANKING = 430
CIVIL_RIGHTS_OTHER = 440
CIVIL_RIGHTS_VOTING = 441
CIVIL_RIGHTS_JOBS = 442
CIVIL_RIGHTS_ACCOMMODATIONS = 443
CIVIL_RIGHTS_WELFARE = 444
CIVIL_RIGHTS_ADA_EMPLOYMENT = 445
CIVIL_RIGHTS_ADA_OTHER = 446
EDUCATION = 448
INTERSTATE_COMMERCE = 450
DEPORTATION = 460
NATURALIZATION_DENIAL = 462
HABEAS_CORPUS_ALIEN_DETAINEE = 463
IMMIGRATION_ACTIONS_OTHER = 465
CIVIL_RICO = 470
CONSUMER_CREDIT = 480
CABLE_SATELLITE_TV = 490
PRISONER_PETITIONS_VACATE_SENTENCE = 510
PRISONER_PETITIONS_HABEAS_CORPUS = 530
HABEAS_CORPUS_DEATH_PENALTY = 535
PRISONER_PETITIONS_MANDAMUS_AND_OTHER = 540
PRISONER_CIVIL_RIGHTS = 550
PRISONER_PRISON_CONDITION = 555
CIVIL_DETAINEE = 560
# Two NOS for same thing!
AGRICULTURAL_ACTS_610 = 610
FOOD_AND_DRUG_ACTS = 620
DRUG_RELATED_SEIZURE_OF_PROPERTY = 625
LIQUOR_LAWS = 630
RAILROAD_AND_TRUCKS = 640
AIRLINE_REGULATIONS = 650
OCCUPATIONAL_SAFETY_HEALTH = 660
FORFEITURE_AND_PENALTY_SUITS_OTHER = 690
FAIR_LABOR_STANDARDS_ACT_CV = 710
LABOR_MANAGEMENT_RELATIONS_ACT = 720
LABOR_MANAGEMENT_REPORT_DISCLOSURE = 730
RAILWAY_LABOR_ACT = 740
FAMILY_AND_MEDICAL_LEAVE_ACT = 751
LABOR_LITIGATION_OTHER = 790
EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT = 791
SELECTIVE_SERVICE = 810
COPYRIGHT = 820
PATENT = 830
TRADEMARK = 840
SECURITIES_COMMODITIES_EXCHANGE = 850
SOCIAL_SECURITY = 860
MEDICARE = 861
BLACK_LUNG = 862
DIWC_DIWW = 863
SSID = 864
RSI = 865
TAX_SUITS = 870
IRS_3RD_PARTY_SUITS = 871
CUSTOMER_CHALLENGE = 875
STATUTORY_ACTIONS_OTHER = 890
# Two NOS for same thing!
AGRICULTURAL_ACTS_891 = 891
ECONOMIC_STABILIZATION_ACT = 892
ENVIRONMENTAL_MATTERS = 893
ENERGY_ALLOCATION_ACT = 894
FREEDOM_OF_INFORMATION_ACT_OF_1974 = 895
ARBITRATION = 896
APA_REVIEW_OR_APPEAL_OF_AGENCY_DECISION = 899
APPEAL_OF_FEE_EQUAL_ACCESS_TO_JUSTICE = 900
DOMESTIC_RELATIONS = 910
INSANITY = 920
PROBATE = 930
SUBSTITUTE_TRUSTEE = 940
CONSTITUTIONALITY_OF_STATE_STATUTES = 950
OTHER = 990
LOCAL_JURISDICTIONAL_APPEAL = 992
MISCELLANEOUS = 999
NOS_CODES = (
    (INSURANCE, 'Insurance'),
    (MARINE_CONTRACT, 'Marine contract actions'),
    (MILLER_ACT, 'Miller act'),
    (NEGOTIABLE_INSTRUMENTS, 'Negotiable instruments'),
    (OVERPAYMENTS_AND_ENFORCEMENTS, 'Overpayments & enforcement of judgments'),
    (OVERPAYMENTS_MEDICARE, 'Overpayments under the medicare act'),
    (RECOVERY_OF_STUDENT_LOANS, 'Recovery of defaulted student loans'),
    (RECOVERY_OF_VET_BENEFITS_OVERPAYMENTS, 'Recovery of overpayments of vet '
                                            'benefits'),
    (STOCKHOLDER_SUITS, "Stockholder's suits"),
    (CONTRACT_OTHER, 'Other contract actions'),
    (CONTRACT_PRODUCT_LIABILITY, 'Contract product liability'),
    (CONTRACT_FRANCHISE, 'Contract franchise'),
    (LAND_CONDEMNATION, 'Land condemnation'),
    (FORECLOSURE, 'Foreclosure'),
    (RENT_LEASE_EJECTMENT, 'Rent, lease, ejectment'),
    (TORT_LAND, 'Torts to land'),
    (TORT_PRODUCT_LIABILITY, 'Tort product liability'),
    (REAL_PROPERTY_ACTIONS_OTHER, 'Other real property actions'),
    (AIRPLANE_PERSONAL_INJURY, 'Airplane personal injury'),
    (AIRPLANE_PRODUCT_LIABILITY, 'Airplane product liability'),
    (ASSAULT_LIBEL_AND_SLANDER, 'Assault, libel, and slander'),
    (FEDERAL_EMPLOYERS_LIABILITY, 'Federal employers\' liability'),
    (MARINE_PERSONAL_INJURY, 'Marine personal injury'),
    (MARINE_PRODUCT_LIABILITY, 'Marine - Product liability'),
    (MOTOR_VEHICLE_PERSONAL_INJURY, 'Motor vehicle personal injury'),
    (MOTOR_VEHICLE_PRODUCT_LIABILITY, 'Motor vehicle product liability'),
    (PERSONAL_INJURY_OTHER, 'Other personal liability'),
    (MEDICAL_MALPRACTICE, 'Medical malpractice'),
    (PERSONAL_INJURY_PRODUCT_LIABILITY, 'Personal injury - Product liability'),
    (HEALTH_CARE_PHARM, 'Health care / pharm'),
    (ASBESTOS_PERSONAL_INJURY, 'Asbestos personal injury - Prod. Liab.'),
    (FRAUD_OTHER, 'Other fraud'),
    (TRUTH_IN_LENDING, 'Truth in lending'),
    (FALSE_CLAIMS_ACT, 'False Claims Act'),
    (PERSONAL_PROPERTY_DAMAGE_OTHER, 'Other personal property damage'),
    (PROPERTY_DAMAGE_PRODUCT_LIABILITY, 'Property damage - Product liability'),
    (STATE_RE_APPORTIONMENT, 'State re-appointment'),
    (ANTITRUST, 'Antitrust'),
    (BANKRUPTCY_APPEALS, 'Bankruptcy appeals rule 28 USC 158'),
    (BANKRUPTCY_WITHDRAWAL, 'Bankruptcy withdrawal 28 USC 157'),
    (BANKS_AND_BANKING, 'Banks and banking'),
    (CIVIL_RIGHTS_OTHER, 'Civil rights other'),
    (CIVIL_RIGHTS_VOTING, 'Civil rights voting'),
    (CIVIL_RIGHTS_JOBS, 'Civil rights jobs'),
    (CIVIL_RIGHTS_ACCOMMODATIONS, 'Civil rights accomodations'),
    (CIVIL_RIGHTS_WELFARE, 'Civil rights welfare'),
    (CIVIL_RIGHTS_ADA_EMPLOYMENT, 'Civil rights ADA employment'),
    (CIVIL_RIGHTS_ADA_OTHER, 'Civil rights ADA other'),
    (EDUCATION, 'Education'),
    (INTERSTATE_COMMERCE, 'Interstate commerce'),
    (DEPORTATION, 'Deportation'),
    (NATURALIZATION_DENIAL, 'Naturalization, petition for hearing of denial'),
    (HABEAS_CORPUS_ALIEN_DETAINEE, 'Habeas corpus - alien detainee'),
    (IMMIGRATION_ACTIONS_OTHER, 'Other immigration actions'),
    (CIVIL_RICO, 'Civil (RICO)'),
    (CONSUMER_CREDIT, 'Consumer credit'),
    (CABLE_SATELLITE_TV, 'Cable/Satellite TV'),
    (PRISONER_PETITIONS_VACATE_SENTENCE,
     'Prisoner petitions - vacate sentence'),
    (PRISONER_PETITIONS_HABEAS_CORPUS, 'Prisoner petitions - habeas corpus'),
    (HABEAS_CORPUS_DEATH_PENALTY, 'Habeas corpus: Death penalty'),
    (PRISONER_PETITIONS_MANDAMUS_AND_OTHER, 'Prisoner petitions - mandamus and '
                                            'other'),
    (PRISONER_CIVIL_RIGHTS, 'Prisoner - civil rights'),
    (PRISONER_PRISON_CONDITION, 'Prisoner - prison condition'),
    (CIVIL_DETAINEE, 'Civil detainee'),
    # Two NOS for same thing!
    (AGRICULTURAL_ACTS_610, 'Agricultural acts'),
    (FOOD_AND_DRUG_ACTS, 'Food and drug acts'),
    (DRUG_RELATED_SEIZURE_OF_PROPERTY, 'Drug related seizure of property'),
    (LIQUOR_LAWS, 'Liquor laws'),
    (RAILROAD_AND_TRUCKS, 'Railroad and trucks'),
    (AIRLINE_REGULATIONS, 'Airline regulations'),
    (OCCUPATIONAL_SAFETY_HEALTH, 'Occupational safety/health'),
    (FORFEITURE_AND_PENALTY_SUITS_OTHER, 'Other forfeiture and penalty suits'),
    (FAIR_LABOR_STANDARDS_ACT_CV, 'Fair Labor Standards Act'),
    (LABOR_MANAGEMENT_RELATIONS_ACT, 'Labor/Management Relations Act'),
    (LABOR_MANAGEMENT_REPORT_DISCLOSURE,
     'Labor/Management report & disclosure'),
    (RAILWAY_LABOR_ACT, 'Railway Labor Act'),
    (FAMILY_AND_MEDICAL_LEAVE_ACT, 'Family and Medical Leave Act'),
    (LABOR_LITIGATION_OTHER, 'Other labor litigation'),
    (EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT,
     'Employee Retirement Income Security Act'),
    (SELECTIVE_SERVICE, 'Selective service'),
    (COPYRIGHT, 'Copyright'),
    (PATENT, 'Patent'),
    (TRADEMARK, 'Trademark'),
    (SECURITIES_COMMODITIES_EXCHANGE, 'Securities, Commodities, Exchange'),
    (SOCIAL_SECURITY, 'Social security'),
    (MEDICARE, 'HIA (1395 FF) / Medicare'),
    (BLACK_LUNG, 'Black lung'),
    (DIWC_DIWW, 'D.I.W.C. / D.I.W.W.'),
    (SSID, 'S.S.I.D.'),
    (RSI, 'R.S.I.'),
    (TAX_SUITS, 'Tax suits'),
    (IRS_3RD_PARTY_SUITS, 'IRS 3rd party suits 26 USC 7609'),
    (CUSTOMER_CHALLENGE, 'Customer challenge 12 USC 3410'),
    (STATUTORY_ACTIONS_OTHER, 'Other statutory actions'),
    # Two NOS for same thing!
    (AGRICULTURAL_ACTS_891, 'Agricultural acts'),
    (ECONOMIC_STABILIZATION_ACT, 'Economic Stabilization Act'),
    (ENVIRONMENTAL_MATTERS, 'Environmental matters'),
    (ENERGY_ALLOCATION_ACT, 'Energy Allocation Act'),
    (FREEDOM_OF_INFORMATION_ACT_OF_1974, 'Freedom of Information Act of 1974'),
    (ARBITRATION, 'Arbitration'),
    (APA_REVIEW_OR_APPEAL_OF_AGENCY_DECISION,
     'Administrative procedure act / review or appeal of agency decision'),
    (APPEAL_OF_FEE_EQUAL_ACCESS_TO_JUSTICE,
     'Appeal of fee - equal access to justice'),
    (DOMESTIC_RELATIONS, 'Domestic relations'),
    (INSANITY, 'Insanity'),
    (PROBATE, 'Probate'),
    (SUBSTITUTE_TRUSTEE, 'Substitute trustee'),
    (CONSTITUTIONALITY_OF_STATE_STATUTES,
     'Constitutionality of state statutes'),
    (OTHER, 'Other'),
    (LOCAL_JURISDICTIONAL_APPEAL, 'Local jurisdictional appeal'),
    (MISCELLANEOUS, 'Miscellaneous'),
)

# Criminal Nature of Offence codes
MURDER_FIRST_DEGREE_0100 = '0100'
MURDER_GOVERNMENT_OFFICIALS = '0101'
MURDER_SECOND_DEGREE = '0200'
MURDER_2ND_DEGREE_GOVERNMENT_OFFICIALS = '0201'
MANSLAUGHTER_300 = '0300'
MANSLAUGHTER_301 = '0301'
NEGLIGENT_HOMICIDE = '0310'
NEGLIGENT_HOMICIDE_GOVERNMENT_OFFICIALS = '0311'
ROBBERY_BANK = '1100'
ROBBERY_POSTAL = '1200'
ROBBERY_OTHER = '1400'
AGGRAVATED_OR_FELONIOUS = '1500'
FELONY_ON_GOVERNMENT_OFFICIAL = '1501'
FAIR_HOUSING_LAW = '1560'
ASSAULT_OTHER = '1600'
MISDEMEANOR_ON_GOVERNMENT_OFFICIAL = '1601'
OBSTRUCTION_OF_JUSTICE_INTERFERENCE = '1602'
RACKETEERING_VIOLENT_CRIME = '1700'
CARJACKING = '1800'
BURGLARY_BANK = '2100'
BURGLARY_POSTAL = '2200'
INTERSTATE_COMMERCE_2300 = '2300'
BURGLARY_OTHER = '2400'
LARCENY_AND_THEFT_BANK = '3100'
LARCENY_AND_THEFT_POSTAL = '3200'
INTERSTATE_COMMERCE_3300 = '3300'
THEFT_OF_US_PROPERTY = '3400'
THEFT_WITHIN_SPECIAL_MARITIME_JURISDICTION = '3500'
TRANSPORTATION_OF_STOLEN_PROPERTY = '3600'
LARCENY_AND_THEFT_FELONY_OTHER = '3700'
LARCENY_AND_THEFT_MISDEMEANOR_OTHER = '3800'
BANK_EMBEZZLEMENT = '4100'
POSTAL_EMBEZZLEMENT = '4200'
EMBEZZLES_PUBLIC_MONEYS_OR_PROPERTY = '4310'
LENDING_CREDIT_INSURANCE_INSTITUTIONS = '4320'
BY_OFFICERS_OF_A_CARRIER = '4330'
WORLD_WAR_VETERANS_RELIEF = '4340'
EMBEZZLEMENT_OFFICER_OR_EMPLOYEE_OF_US_GOVT = '4350'
EMBEZZLEMENT_OTHER = '4390'
INCOME_TAX_EVADE_OR_DEFEAT = '4510'
INCOME_TAX_OTHER_FELONY = '4520'
INCOME_TAX_FAILURE_TO_FILE = '4530'
INCOME_TAX_OTHER_MISDEMEANOR = '4540'
LENDING_CREDIT_INSTITUTIONS = '4600'
BANK_FRAUD = '4601'
POSTAL_INTERSTATE_WIRE_RADIO_ETC = '4700'
VETERANS_AND_ALLOTMENTS = '4800'
BANKRUPTCY = '4900'
MARKETING_AGREEMENTS_AND_COMMODITY_CREDIT = '4910'
SECURITIES_AND_EXCHANGE = '4920'
FRAUD_EXCISE_TAX_OTHER = '4931'
FRAUD_WAGERING_TAX_OTHER = '4932'
FRAUD_OTHER_TAX_4933 = '4933'
RAILROAD_RETIREMENT_AND_UNEMPLOYMENT = '4940'
FRAUD_FOOD_STAMP_PROGRAM = '4941'
SOCIAL_SECURITY_4950 = '4950'
FALSE_PERSONATION = '4960'
NATIONALITY_LAWS = '4970'
PASSPORT_FRAUD = '4980'
FALSE_CLAIMS_AND_STATEMENTS = '4991'
FRAUD_CONSPIRACY_TO_DEFRAUD_OTHER = '4992'
FRAUD_CONSPIRACY_GENERAL_OTHER = '4993'
FRAUD_FALSE_ENTRIES_OTHER = '4994'
CREDIT_CARD_FRAUD = '4995'
COMPUTER_FRAUD = '4996'
TELEMARKETING_FRAUD = '4997'
HEALTH_CARE_FRAUD = '4998'
FRAUD_OTHER_4999 = '4999'
TRANSPORT_ETC_STOLEN_VEHICLES_AIRCRAFT = '5100'
AUTO_THEFT_OTHER = '5200'
TRANSPORT_FORGED_SECURITIES = '5500'
FORGERY_POSTAL = '5600'
FORGERY_OTHER_U_S = '5710'
FORGERY_OTHER = '5720'
COUNTERFEITING = '5800'
SEXUALLY_EXPLICIT_MATERIAL = '5900'
SEXUAL_ABUSE_OF_ADULT = '6100'
SEXUAL_ABUSE_OF_CHILDREN = '6110'
INTERSTATE_DOMESTIC_VIOLENCE = '6120'
VIOLENT_OFFENSES_OTHER = '6121'
WHITE_SLAVE_AND_IMPORTING_ALIENS = '6200'
SEX_OFFENSES_OTHER = '6300'
TRANSPORTATION_FOR_ILLEGAL_SEXUAL_ACTIVITY = '6301'
FAILURE_TO_REGISTER = '6400'
NARC_MARIJUANA_TAX_ACT_TERMS_REOPENS = '6500'
MARIJUANA_SELL_DISTRIBUTE_OR_DISPENSE = '6501'
MARIJUANA_IMPORTATION_EXPORTATION = '6502'
MARIJUANA_MANUFACTURE = '6503'
MARIJUANA_POSSESSION = '6504'
MARIJUANA_RECORDS_RX_S_FRAUDULENT_RX = '6505'
NARC_BORDER_REGISTRATION_TERMS_REOPENS = '6600'
NARCOTICS_OTHER_TERMS_REOPENS = '6700'
NARCOTICS_SELL_DISTRIBUTE_OR_DISPENSE = '6701'
NARCOTICS_IMPORTATION_EXPORTATION = '6702'
NARCOTICS_MANUFACTURE = '6703'
NARCOTICS_POSSESSION = '6704'
NARCOTICS_RECORDS_RX_S_FRAUDULENT_RX_S = '6705'
NARCOTICS_OTHER_TERMS_REOPENS_6706 = '6706'
NARCOTICS_OTHER_TERMS_REOPENS_6707 = '6707'
CONTINUING_CRIMINAL_ENTERPRISE = '6800'
CONTROLLED_SUBSTANCE_SELL_DISTRIBUTE_OR_DISPENSE = '6801'
CONTROLLED_SUBSTANCE_IMPORTATION_EXPORTATION = '6802'
CONTROLLED_SUBSTANCE_MANUFACTURE = '6803'
CONTROLLED_SUBSTANCE_POSSESSION = '6804'
CONTROL_SUBSTANCE_RECORDS_RX_S_FRAUDULENT_RX_S = '6805'
DRUG_CULTIVATION = '6806'
ILLICIT_DRUG_PROFITS_6807 = '6807'
CONTROLLED_SUBSTANCES_ABOARD_AIRCRAFT = '6808'
MAIL_ORDER_DRUG_PARAPHERNALIA_6809 = '6809'
UNDER_INFLUENCE_ALCOHOL_DRUGS = '6810'
POLLUTING_FEDERAL_LANDS_CONTROLLED_SUBSTANCE = '6900'
OTHER_DRUG_OFFENSES = '6905'
ILLICIT_DRUG_PROFITS_6907 = '6907'
MAIL_ORDER_DRUG_PARAPHERNALIA_6909 = '6909'
OTHER_DAPCA_OFFENSES = '6911'
BRIBERY = '7100'
CONFLICT_OF_INTEREST_MINING = '7130'
CONFLICT_OF_INTEREST_HEALTH_WELFARE = '7131'
TRAFFIC_OFFENSES_DRUNKEN_DRIVING = '7210'
TRAFFIC_OFFENSES_OTHER = '7220'
ESCAPE = '7310'
ESCAPE_JUMPING_BAIL = '7311'
ESCAPE_BAIL_REFORM_ACT_OF_1966 = '7312'
ESCAPE_FROM_CUSTODY = '7313'
CRIMINAL_DEFAULT = '7314'
ESCAPE_AIDING_OR_HARBORING = '7320'
PRISON_CONTRABAND = '7330'
FRAUD_OTHER_7331 = '7331'
EXTORTION_RACKETEERING_AND_THREATS = '7400'
THREATS_AGAINST_THE_PRESIDENT = '7401'
RACKETEERING_ARSON = '7410'
RACKETEERING_BRIBERY = '7420'
RACKETEERING_EXTORTION = '7430'
RACKETEERING_GAMBLING = '7440'
RACKETEERING_LIQUOR = '7450'
RACKETEERING_NARCOTICS = '7460'
RACKETEERING_PROSTITUTION = '7470'
RACKETEERING_MURDER = '7471'
RACKETEERING_KIDNAP = '7472'
RACKETEERING_MAIM = '7473'
CONSPIRACY_MURDER_KIDNAP = '7474'
ATTEMPT_CONSPIRE_MAIM_ASSAULT = '7475'
MONETARY_LAUNDERING = '7477'
MURDER_FIRST_DEGREE_7478 = '7478'
RACKETEERING = '7480'
RACKETEERING_ROBBERY = '7481'
RACKETEERING_THREATS = '7482'
RACKETEERING_EXTORTION_CREDIT_TRANSACTION = '7490'
GAMBLING_AND_LOTTERY = '7500'
GAMBLING_AND_LOTTERY_TRAVEL_RACKETEERING = '7520'
GAMBLING_AND_LOTTERY_TRANSMIT_WAGER_INFO = '7530'
KIDNAPPING_18_1201_1202 = '7600'
KIDNAPPING_GOVT_OFFICIALS = '7601'
KIDNAPPING_18_13 = '7610'
KIDNAP_HOSTAGE = '7611'
PERJURY = '7700'
FIREARMS_AND_WEAPONS = '7800'
FIREARMS_UNLAWFUL_POSSESSION = '7820'
FIREARMS = '7830'
FURTHERANCE_OF_VIOLENCE = '7831'
ARSON = '7910'
ABORTION = '7920'
BIGAMY = '7930'
MALICIOUS_DESTRUCTION_OF_PROPERTY = '7940'
OTHER_PROPERTY = '7941'
DISORDERLY_CONDUCT = '7950'
TRAVEL_TO_INCITE_TO_RIOT = '7961'
CIVIL_DISORDER = '7962'
MISC_GENERAL_OFFENSES_OTHER = '7990'
JUVENILE_DELINQUENCY = '7991'
FAILURE_TO_PAY_CHILD_SUPPORT = '8100'
FALSE_CLAIMS_AND_SERVICES_GOVERNMENT = '8200'
IDENTIFICATION_DOCUMENTS_AND_INFORMATION_FRAUD = '8201'
MAIL_FRAUD = '8500'
WIRE_RADIO_OR_TELEVISION_FRAUD = '8600'
IMMIGRATION_LAWS_ILLEGAL_ENTRY_8710 = '8710'
IMMIGRATION_LAWS_ILLEGAL_RE_ENTRY = '8720'
IMMIGRATION_LAWS_OTHER = '8730'
FRAUD_AND_MISUSE_OF_VISA_PERMITS = '8731'
IMMIGRATION_LAWS_ILLEGAL_ENTRY_8740 = '8740'
IMMIGRATION_LAWS_FRAUDULENT_CITIZENSHIP = '8750'
LIQUOR_INTERNAL_REVENUE = '8900'
FRAUD_OTHER_TAX_8901 = '8901'
HAZARDOUS_WASTE_TREATMENT_DISPOSAL_STORE = '9001'
AGRICULTURE_ACTS_9110 = '9110'
AGRICULTURE_ACTS_9115 = '9115'
AGRICULTURE_FEDERAL_SEED_ACT = '9120'
GAME_CONSERVATION_ACTS = '9130'
AGRICULTURE_INSECTICIDE_ACT = '9140'
NATIONAL_PARK_RECREATION_VIOLATIONS_9150 = '9150'
AGRICULTURE_PACKERS_AND_STOCKYARD_ACT = '9160'
AGRICULTURE_PLANT_QUARANTINE = '9170'
AGRICULTURE_HANDLING_ANIMALS_RESEARCH = '9180'
ANTITRUST_VIOLATIONS = '9200'
FAIR_LABOR_STANDARDS_ACT_CR = '9300'
FOOD_AND_DRUG_ACT = '9400'
MIGRATORY_BIRD_LAWS = '9500'
MOTOR_CARRIER_ACT = '9600'
NATIONAL_DEFENSE_SELECTIVE_SERVICE_ACTS = '9710'
NATIONAL_DEFENSE_ILLEGAL_USE_OF_UNIFORM = '9720'
NATIONAL_DEFENSE_DEFENSE_PRODUCTION_ACT = '9730'
ECONOMIC_STABILIZATION_ACT_OF_1970_PRICE = '9731'
ECONOMIC_STABILIZATION_ACT_OF_1970_RENTS = '9732'
ECONOMIC_STABILIZATION_ACT_OF_1970_WAGES = '9733'
ALIEN_REGISTRATION = '9740'
ENERGY_FACILITY = '9741'
TREASON = '9751'
ESPIONAGE = '9752'
SABOTAGE = '9753'
SEDITION = '9754'
SMITH_ACT = '9755'
CURFEW_RESTRICTED_AREAS = '9760'
EXPORTATION_OF_WAR_MATERIALS = '9770'
ANTI_APARTHEID_PROGRAM = '9771'
TRADING_WITH_THE_ENEMY_ACT = '9780'
NATIONAL_DEFENSE_OTHER = '9790'
SUBVERSIVE_ACTIVITIES_CONTROL_ACT = '9791'
DEFENSE_CONTRACTORS = '9792'
ARMED_FORCES = '9793'
OBSCENE_MAIL = '9810'
OBSCENE_MATTER_IN_INTERSTATE_COMMERCE = '9820'
CIVIL_RIGHTS = '9901'
ELECTION_LAW_VIOLATORS = '9902'
FEDERAL_STATUES_PUBLIC_OFFICER_EMPLOYEES = '9903'
FEDERAL_STATUTE_US_EMBLEMS_INSIGNIAS = '9904'
FEDERAL_STATUTES_FOREIGN_RELATIONS = '9905'
FEDERAL_STATUTES_BANK_AND_BANKING = '9906'
FEDERAL_STATUTES_MONEY_AND_FINANCE = '9907'
FEDERAL_STATUTES_PUBLIC_HEALTH_AND_WELFARE = '9908'
FEDERAL_STATUTE_CENSUS = '9909'
COMMUNICATION_ACTS_INCLUDING_WIRE_TAPPING = '9910'
WIRE_INTERCEPTION = '9911'
FEDERAL_STATUTES_COPYRIGHT_LAWS = '9912'
FEDERAL_STATUTES_COAST_GUARD = '9914'
FEDERAL_STATUTES_COMMERCE_AND_TRADE = '9915'
FEDERAL_STATUTES_CONSUMER_CREDIT_PROTECTION = '9916'
FEDERAL_STATUTES_CONSUMER_PRODUCT_SAFETY = '9917'
FEDERAL_STATUES_TOXIC_SUBSTANCE_CONTROL = '9918'
FEDERAL_STATUTES_TITLE_5 = '9919'
FEDERAL_STATUTES_CONSERVATION_ACTS = '9920'
CONTEMPT = '9921'
CONTEMPT_CONGRESSIONAL = '9922'
FORFEITURE_CRIMINAL_OR_DRUG_RELATED = '9923'
FEDERAL_STATUTES_EXTORT_OPPRESS_UNDER_LAW = '9926'
FEDERAL_STATUTES_REMOVAL_FROM_STATE_COURT = '9928'
FEDERAL_STATUTES_LABOR_LAWS = '9929'
FEDERAL_STATUTES_MINERALS_AND_LAND_MINING = '9930'
CUSTOMS_LAWS_EXCEPT_NARCOTICS_AND_LIQUOR = '9931'
CUSTOMS_LAWS_IMPORT_INJURIOUS_ANIMALS = '9932'
PATENTS_AND_TRADEMARKS = '9935'
PATRIOTIC_SOCIETIES_AND_OBSERVANCES = '9936'
VETERANS_BENEFITS = '9938'
SOCIAL_SECURITY_9940 = '9940'
CONNALLY_ACT_HOT_OIL_ACT = '9941'
TRANSPORT_CONVICT_MADE_GOODS_INTERSTATE = '9942'
RAILROAD_AND_TRANSPORTATION_ACTS = '9943'
DESTRUCTION_OF_PROPERTY_INTERSTATE_COMMERCE = '9944'
TELEPHONES_TELEGRAPHS_AND_RADIOS = '9947'
FEDERAL_STATUTE_TRANSPORTATION = '9949'
WAR_AND_NATIONAL_DEFENSE_OTHER = '9950'
TRANSPORTATION_OF_STRIKEBREAKERS = '9951'
TAFT_HARTLEY_ACT = '9952'
EIGHT_HOUR_DAY_ON_PUBLIC_WORKS = '9953'
PEONAGE = '9954'
FEDERAL_STATUTE_PHW = '9956'
TERRORIST_ACTIVITY = '9957'
LIQUOR_EXCEPT_INTERNAL_REVENUE = '9960'
MARITIME_AND_SHIPPING_LAWS = '9971'
STOWAWAYS = '9972'
FEDERAL_BOAT_SAFETY_ACT_OF_1971 = '9973'
FEDERAL_WATER_POLLUTION_CONTROL_ACT = '9974'
POSTAL_NON_MAILABLE_MATERIAL = '9981'
POSTAL_INJURY_TO_PROPERTY = '9982'
POSTAL_OBSTRUCTING_THE_MAIL = '9983'
POSTAL_VIOLATIONS_BY_POSTAL_EMPLOYEES = '9984'
POSTAL_OTHER = '9989'
NATIONAL_PARK_RECREATION_VIOLATIONS_9990 = '9990'
DESTROYING_FEDERAL_PROPERTY = '9991'
INTIMIDATION_OF_WITNESSES_JURORS_ETC = '9992'
AIRCRAFT_REGULATIONS = '9993'
EXPLOSIVES_EXCEPT_ON_VESSELS = '9994'
GOLD_ACTS = '9995'
TRAIN_WRECKING = '9996'
FEDERAL_STATUTES_OTHER = '9999'
NOO_CODES = (
    (MURDER_FIRST_DEGREE_0100, 'Murder, First Degree'),
    (MURDER_GOVERNMENT_OFFICIALS, 'Murder, Government Officials'),
    (MURDER_SECOND_DEGREE, 'Murder, Second Degree'),
    (MURDER_2ND_DEGREE_GOVERNMENT_OFFICIALS,
     'Murder, 2nd Degree, Government Officials'),
    (MANSLAUGHTER_300, 'Manslaughter'),
    (MANSLAUGHTER_301, 'Manslaughter'),
    (NEGLIGENT_HOMICIDE, 'Negligent Homicide'),
    (NEGLIGENT_HOMICIDE_GOVERNMENT_OFFICIALS,
     'Negligent Homicide, Government Officials'),
    (ROBBERY_BANK, 'Robbery, Bank'),
    (ROBBERY_POSTAL, 'Robbery, Postal'),
    (ROBBERY_OTHER, 'Robbery, Other'),
    (AGGRAVATED_OR_FELONIOUS, 'Aggravated or Felonious'),
    (FELONY_ON_GOVERNMENT_OFFICIAL, 'Felony, on Government Official'),
    (FAIR_HOUSING_LAW, 'Fair Housing Law'),
    (ASSAULT_OTHER, 'Assault, Other'),
    (MISDEMEANOR_ON_GOVERNMENT_OFFICIAL, 'Misdemeanor, on Government Official'),
    (OBSTRUCTION_OF_JUSTICE_INTERFERENCE,
     'Obstruction of Justice-Interference'),
    (RACKETEERING_VIOLENT_CRIME, 'Racketeering, Violent Crime'),
    (CARJACKING, 'Carjacking'),
    (BURGLARY_BANK, 'Burglary, Bank'),
    (BURGLARY_POSTAL, 'Burglary, Postal'),
    (INTERSTATE_COMMERCE_2300, 'Interstate Commerce'),
    (BURGLARY_OTHER, 'Burglary, Other'),
    (LARCENY_AND_THEFT_BANK, 'Larceny & Theft, Bank'),
    (LARCENY_AND_THEFT_POSTAL, 'Larceny & Theft, Postal'),
    (INTERSTATE_COMMERCE_3300, 'Interstate Commerce'),
    (THEFT_OF_US_PROPERTY, 'Theft of U.S. Property'),
    (THEFT_WITHIN_SPECIAL_MARITIME_JURISDICTION,
     'Theft within Special Maritime Jurisdiction'),
    (TRANSPORTATION_OF_STOLEN_PROPERTY, 'Transportation of Stolen Property'),
    (LARCENY_AND_THEFT_FELONY_OTHER, 'Larceny & Theft, Felony Other'),
    (LARCENY_AND_THEFT_MISDEMEANOR_OTHER,
     'Larceny & Theft, Misdemeanor Other'),
    (BANK_EMBEZZLEMENT, 'Bank Embezzlement'),
    (POSTAL_EMBEZZLEMENT, 'Postal Embezzlement'),
    (EMBEZZLES_PUBLIC_MONEYS_OR_PROPERTY,
     'Embezzles Public Moneys Or Property'),
    (LENDING_CREDIT_INSURANCE_INSTITUTIONS,
     'Lending, Credit, Insurance Institutions'),
    (BY_OFFICERS_OF_A_CARRIER, 'By Officers Of A Carrier'),
    (WORLD_WAR_VETERANS_RELIEF, 'World War Veterans Relief'),
    (EMBEZZLEMENT_OFFICER_OR_EMPLOYEE_OF_US_GOVT,
     'Embezzlement: Officer or Employee of U.S. Govt.'),
    (EMBEZZLEMENT_OTHER, 'Embezzlement, Other'),
    (INCOME_TAX_EVADE_OR_DEFEAT, 'Income Tax, Evade or Defeat'),
    (INCOME_TAX_OTHER_FELONY, 'Income Tax, Other Felony'),
    (INCOME_TAX_FAILURE_TO_FILE, 'Income Tax, Failure to File'),
    (INCOME_TAX_OTHER_MISDEMEANOR, 'Income Tax, Other Misdemeanor'),
    (LENDING_CREDIT_INSTITUTIONS, 'Lending, Credit Institutions'),
    (BANK_FRAUD, 'Bank Fraud'),
    (POSTAL_INTERSTATE_WIRE_RADIO_ETC, 'Postal, Interstate Wire, Radio, etc.'),
    (VETERANS_AND_ALLOTMENTS, 'Veterans and Allotments'),
    (BANKRUPTCY, 'Bankruptcy'),
    (MARKETING_AGREEMENTS_AND_COMMODITY_CREDIT,
     'Marketing Agreements & Commodity Credit'),
    (SECURITIES_AND_EXCHANGE, 'Securities & Exchange'),
    (FRAUD_EXCISE_TAX_OTHER, 'Fraud, Excise Tax, Other'),
    (FRAUD_WAGERING_TAX_OTHER, 'Fraud, Wagering Tax, Other'),
    (FRAUD_OTHER_TAX_4933, 'Fraud, Other Tax'),
    (RAILROAD_RETIREMENT_AND_UNEMPLOYMENT,
     'Railroad Retirement & Unemployment'),
    (FRAUD_FOOD_STAMP_PROGRAM, 'Fraud Food Stamp Program'),
    (SOCIAL_SECURITY_4950, 'Social Security'),
    (FALSE_PERSONATION, 'False Personation'),
    (NATIONALITY_LAWS, 'Nationality Laws'),
    (PASSPORT_FRAUD, 'Passport Fraud'),
    (FALSE_CLAIMS_AND_STATEMENTS, 'False Claims & Statements'),
    (FRAUD_CONSPIRACY_TO_DEFRAUD_OTHER, 'Fraud, Conspiracy to Defraud, Other'),
    (FRAUD_CONSPIRACY_GENERAL_OTHER, 'Fraud, Conspiracy (General), Other'),
    (FRAUD_FALSE_ENTRIES_OTHER, 'Fraud, False Entries, Other'),
    (CREDIT_CARD_FRAUD, 'Credit Card Fraud'),
    (COMPUTER_FRAUD, 'Computer Fraud'),
    (TELEMARKETING_FRAUD, 'Telemarketing Fraud'),
    (HEALTH_CARE_FRAUD, 'Health Care Fraud'),
    (FRAUD_OTHER_4999, 'Fraud, Other'),
    (TRANSPORT_ETC_STOLEN_VEHICLES_AIRCRAFT,
     'Transport etc. Stolen Vehicles, Aircraft'),
    (AUTO_THEFT_OTHER, 'Auto Theft, Other'),
    (TRANSPORT_FORGED_SECURITIES, 'Transport, Forged Securities'),
    (FORGERY_POSTAL, 'Forgery, Postal'),
    (FORGERY_OTHER_U_S, 'Forgery, Other U. S.'),
    (FORGERY_OTHER, 'Forgery, Other'),
    (COUNTERFEITING, 'Counterfeiting'),
    (SEXUALLY_EXPLICIT_MATERIAL, 'Sexually Explicit Material'),
    (SEXUAL_ABUSE_OF_ADULT, 'Sexual Abuse of Adult'),
    (SEXUAL_ABUSE_OF_CHILDREN, 'Sexual Abuse of Children'),
    (INTERSTATE_DOMESTIC_VIOLENCE, 'Interstate Domestic Violence'),
    (VIOLENT_OFFENSES_OTHER, 'Violent Offenses, Other'),
    (WHITE_SLAVE_AND_IMPORTING_ALIENS, 'White Slave & Importing Aliens'),
    (SEX_OFFENSES_OTHER, 'Sex Offenses, Other'),
    (TRANSPORTATION_FOR_ILLEGAL_SEXUAL_ACTIVITY,
     'Transportation for Illegal Sexual Activity'),
    (FAILURE_TO_REGISTER, 'Failure to Register'),
    (NARC_MARIJUANA_TAX_ACT_TERMS_REOPENS,
     'Narc. Marijuana Tax Act (Terms/Reopens)'),
    (MARIJUANA_SELL_DISTRIBUTE_OR_DISPENSE,
     'Marijuana-Sell, Distribute, or Dispense'),
    (MARIJUANA_IMPORTATION_EXPORTATION, 'Marijuana-Importation/Exportation'),
    (MARIJUANA_MANUFACTURE, 'Marijuana-Manufacture'),
    (MARIJUANA_POSSESSION, 'Marijuana-Possession'),
    (MARIJUANA_RECORDS_RX_S_FRAUDULENT_RX,
     'Marijuana-Records, Rx\'s, Fraudulent Rx'),
    (NARC_BORDER_REGISTRATION_TERMS_REOPENS,
     'Narc. Border Registration (Terms/Reopens)'),
    (NARCOTICS_OTHER_TERMS_REOPENS, 'Narcotics, Other (Terms/Reopens)'),
    (NARCOTICS_SELL_DISTRIBUTE_OR_DISPENSE,
     'Narcotics-Sell, Distribute, or Dispense'),
    (NARCOTICS_IMPORTATION_EXPORTATION, 'Narcotics-Importation/Exportation'),
    (NARCOTICS_MANUFACTURE, 'Narcotics-Manufacture'),
    (NARCOTICS_POSSESSION, 'Narcotics-Possession'),
    (NARCOTICS_RECORDS_RX_S_FRAUDULENT_RX_S,
     'Narcotics-Records, Rx\'S, Fraudulent Rx\'s'),
    (NARCOTICS_OTHER_TERMS_REOPENS_6706, 'Narcotics, Other (Terms/Reopens)'),
    (NARCOTICS_OTHER_TERMS_REOPENS_6707, 'Narcotics, Other (Terms/Reopens)'),
    (CONTINUING_CRIMINAL_ENTERPRISE, 'Continuing Criminal Enterprise'),
    (CONTROLLED_SUBSTANCE_SELL_DISTRIBUTE_OR_DISPENSE,
     'Controlled Substance-Sell, Distribute, or Dispense'),
    (CONTROLLED_SUBSTANCE_IMPORTATION_EXPORTATION,
     'Controlled Substance-Importation/Exportation'),
    (CONTROLLED_SUBSTANCE_MANUFACTURE, 'Controlled Substance-Manufacture'),
    (CONTROLLED_SUBSTANCE_POSSESSION, 'Controlled Substance-Possession'),
    (CONTROL_SUBSTANCE_RECORDS_RX_S_FRAUDULENT_RX_S,
     'Control Substance-Records, Rx\'s, Fraudulent Rx\'s'),
    (DRUG_CULTIVATION, 'Drug Cultivation'),
    (ILLICIT_DRUG_PROFITS_6807, 'Illicit Drug Profits'),
    (CONTROLLED_SUBSTANCES_ABOARD_AIRCRAFT,
     'Controlled Substances Aboard Aircraft'),
    (MAIL_ORDER_DRUG_PARAPHERNALIA_6809, 'Mail Order Drug Paraphernalia'),
    (UNDER_INFLUENCE_ALCOHOL_DRUGS, 'Under Influence Alcohol/Drugs'),
    (POLLUTING_FEDERAL_LANDS_CONTROLLED_SUBSTANCE,
     'Polluting Federal Lands-Controlled Substance'),
    (OTHER_DRUG_OFFENSES, 'Other Drug Offenses'),
    (ILLICIT_DRUG_PROFITS_6907, 'Illicit Drug Profits'),
    (MAIL_ORDER_DRUG_PARAPHERNALIA_6909, 'Mail Order Drug Paraphernalia'),
    (OTHER_DAPCA_OFFENSES, 'Other DAPCA Offenses'),
    (BRIBERY, 'Bribery'),
    (CONFLICT_OF_INTEREST_MINING, 'Conflict of Interest-Mining'),
    (CONFLICT_OF_INTEREST_HEALTH_WELFARE,
     'Conflict of Interest-Health/Welfare'),
    (TRAFFIC_OFFENSES_DRUNKEN_DRIVING, 'Traffic Offenses, Drunken Driving'),
    (TRAFFIC_OFFENSES_OTHER, 'Traffic Offenses, Other'),
    (ESCAPE, 'Escape'),
    (ESCAPE_JUMPING_BAIL, 'Escape, Jumping Bail'),
    (ESCAPE_BAIL_REFORM_ACT_OF_1966, 'Escape, Bail Reform Act of 1966'),
    (ESCAPE_FROM_CUSTODY, 'Escape from Custody'),
    (CRIMINAL_DEFAULT, 'Criminal Default'),
    (ESCAPE_AIDING_OR_HARBORING, 'Escape, Aiding or Harboring'),
    (PRISON_CONTRABAND, 'Prison Contraband'),
    (FRAUD_OTHER_7331, 'Fraud, Other'),
    (EXTORTION_RACKETEERING_AND_THREATS, 'Extortion, Racketeering, & Threats'),
    (THREATS_AGAINST_THE_PRESIDENT, 'Threats Against The President'),
    (RACKETEERING_ARSON, 'Racketeering, Arson'),
    (RACKETEERING_BRIBERY, 'Racketeering, Bribery'),
    (RACKETEERING_EXTORTION, 'Racketeering, Extortion'),
    (RACKETEERING_GAMBLING, 'Racketeering, Gambling'),
    (RACKETEERING_LIQUOR, 'Racketeering, Liquor'),
    (RACKETEERING_NARCOTICS, 'Racketeering, Narcotics'),
    (RACKETEERING_PROSTITUTION, 'Racketeering, Prostitution'),
    (RACKETEERING_MURDER, 'Racketeering, Murder'),
    (RACKETEERING_KIDNAP, 'Racketeering, Kidnap'),
    (RACKETEERING_MAIM, 'Racketeering, Maim'),
    (CONSPIRACY_MURDER_KIDNAP, 'Conspiracy, Murder, Kidnap'),
    (ATTEMPT_CONSPIRE_MAIM_ASSAULT, 'Attempt, Conspire/Maim, Assault'),
    (MONETARY_LAUNDERING, 'Monetary Laundering'),
    (MURDER_FIRST_DEGREE_7478, 'Murder, First Degree'),
    (RACKETEERING, 'Racketeering'),
    (RACKETEERING_ROBBERY, 'Racketeering, Robbery'),
    (RACKETEERING_THREATS, 'Racketeering, Threats'),
    (RACKETEERING_EXTORTION_CREDIT_TRANSACTION,
     'Racketeering, Extortion Credit Transaction'),
    (GAMBLING_AND_LOTTERY, 'Gambling & Lottery'),
    (GAMBLING_AND_LOTTERY_TRAVEL_RACKETEERING,
     'Gambling & Lottery, Travel/Racketeering'),
    (GAMBLING_AND_LOTTERY_TRANSMIT_WAGER_INFO,
     'Gambling & Lottery, Transmit Wager Info.'),
    (KIDNAPPING_18_1201_1202, 'Kidnapping (18:1201,1202)'),
    (KIDNAPPING_GOVT_OFFICIALS, 'Kidnapping, Govt Officials'),
    (KIDNAPPING_18_13, 'Kidnapping (18:13)'),
    (KIDNAP_HOSTAGE, 'Kidnap, Hostage'),
    (PERJURY, 'Perjury'),
    (FIREARMS_AND_WEAPONS, 'Firearms & Weapons'),
    (FIREARMS_UNLAWFUL_POSSESSION, 'Firearms, Unlawful Possession'),
    (FIREARMS, 'Firearms'),
    (FURTHERANCE_OF_VIOLENCE, 'Furtherance of Violence'),
    (ARSON, 'Arson'),
    (ABORTION, 'Abortion'),
    (BIGAMY, 'Bigamy'),
    (MALICIOUS_DESTRUCTION_OF_PROPERTY, 'Malicious Destruction of Property'),
    (OTHER_PROPERTY, 'Other, Property'),
    (DISORDERLY_CONDUCT, 'Disorderly Conduct'),
    (TRAVEL_TO_INCITE_TO_RIOT, 'Travel to Incite to Riot'),
    (CIVIL_DISORDER, 'Civil Disorder'),
    (MISC_GENERAL_OFFENSES_OTHER, 'Misc. General Offenses, Other'),
    (JUVENILE_DELINQUENCY, 'Juvenile Delinquency'),
    (FAILURE_TO_PAY_CHILD_SUPPORT, 'Failure to Pay Child Support'),
    (FALSE_CLAIMS_AND_SERVICES_GOVERNMENT,
     'False Claims and Services, Government'),
    (IDENTIFICATION_DOCUMENTS_AND_INFORMATION_FRAUD,
     'Identification Documents and Information Fraud'),
    (MAIL_FRAUD, 'Mail Fraud'),
    (WIRE_RADIO_OR_TELEVISION_FRAUD, 'Wire, Radio, or Television Fraud'),
    (IMMIGRATION_LAWS_ILLEGAL_ENTRY_8710, 'Immigration Laws, Illegal Entry'),
    (IMMIGRATION_LAWS_ILLEGAL_RE_ENTRY, 'Immigration Laws, Illegal Re-Entry'),
    (IMMIGRATION_LAWS_OTHER, 'Immigration Laws, Other'),
    (FRAUD_AND_MISUSE_OF_VISA_PERMITS, 'Fraud And Misuse of Visa/Permits'),
    (IMMIGRATION_LAWS_ILLEGAL_ENTRY_8740, 'Immigration Laws, Illegal Entry'),
    (IMMIGRATION_LAWS_FRAUDULENT_CITIZENSHIP,
     'Immigration Laws, Fraudulent Citizenship'),
    (LIQUOR_INTERNAL_REVENUE, 'Liquor, Internal Revenue'),
    (FRAUD_OTHER_TAX_8901, 'Fraud, Other Tax'),
    (HAZARDOUS_WASTE_TREATMENT_DISPOSAL_STORE,
     'Hazardous Waste-Treatment/Disposal/Store'),
    (AGRICULTURE_ACTS_9110, 'Agriculture Acts'),
    (AGRICULTURE_ACTS_9115, 'Agriculture Acts'),
    (AGRICULTURE_FEDERAL_SEED_ACT, 'Agriculture, Federal Seed Act'),
    (GAME_CONSERVATION_ACTS, 'Game Conservation Acts'),
    (AGRICULTURE_INSECTICIDE_ACT, 'Agriculture, Insecticide Act'),
    (NATIONAL_PARK_RECREATION_VIOLATIONS_9150,
     'National Park/Recreation Violations'),
    (AGRICULTURE_PACKERS_AND_STOCKYARD_ACT,
     'Agriculture, Packers & Stockyard Act'),
    (AGRICULTURE_PLANT_QUARANTINE, 'Agriculture, Plant Quarantine'),
    (AGRICULTURE_HANDLING_ANIMALS_RESEARCH,
     'Agriculture, Handling Animals, Research'),
    (ANTITRUST_VIOLATIONS, 'Antitrust Violations'),
    (FAIR_LABOR_STANDARDS_ACT_CR, 'Fair Labor Standards Act'),
    (FOOD_AND_DRUG_ACT, 'Food & Drug Act'),
    (MIGRATORY_BIRD_LAWS, 'Migratory Bird Laws'),
    (MOTOR_CARRIER_ACT, 'Motor Carrier Act'),
    (NATIONAL_DEFENSE_SELECTIVE_SERVICE_ACTS,
     'National Defense, Selective Service Acts'),
    (NATIONAL_DEFENSE_ILLEGAL_USE_OF_UNIFORM,
     'National Defense, Illegal Use of Uniform'),
    (NATIONAL_DEFENSE_DEFENSE_PRODUCTION_ACT,
     'National Defense, Defense Production Act'),
    (ECONOMIC_STABILIZATION_ACT_OF_1970_PRICE,
     'Economic Stabilization Act of 1970-Price'),
    (ECONOMIC_STABILIZATION_ACT_OF_1970_RENTS,
     'Economic Stabilization Act of 1970-Rents'),
    (ECONOMIC_STABILIZATION_ACT_OF_1970_WAGES,
     'Economic Stabilization Act of 1970-Wages'),
    (ALIEN_REGISTRATION, 'Alien Registration'),
    (ENERGY_FACILITY, 'Energy Facility'),
    (TREASON, 'Treason'),
    (ESPIONAGE, 'Espionage'),
    (SABOTAGE, 'Sabotage'),
    (SEDITION, 'Sedition'),
    (SMITH_ACT, 'Smith Act'),
    (CURFEW_RESTRICTED_AREAS, 'Curfew, Restricted Areas'),
    (EXPORTATION_OF_WAR_MATERIALS, 'Exportation of War Materials'),
    (ANTI_APARTHEID_PROGRAM, 'Anti-Apartheid Program'),
    (TRADING_WITH_THE_ENEMY_ACT, 'Trading with the Enemy Act'),
    (NATIONAL_DEFENSE_OTHER, 'National Defense, Other'),
    (SUBVERSIVE_ACTIVITIES_CONTROL_ACT, 'Subversive Activities Control Act'),
    (DEFENSE_CONTRACTORS, 'Defense Contractors'),
    (ARMED_FORCES, 'Armed Forces'),
    (OBSCENE_MAIL, 'Obscene Mail'),
    (OBSCENE_MATTER_IN_INTERSTATE_COMMERCE,
     'Obscene Matter in Interstate Commerce'),
    (CIVIL_RIGHTS, 'Civil Rights'),
    (ELECTION_LAW_VIOLATORS, 'Election Law Violators'),
    (FEDERAL_STATUES_PUBLIC_OFFICER_EMPLOYEES,
     'Federal Statues-Public Officer/Employees'),
    (FEDERAL_STATUTE_US_EMBLEMS_INSIGNIAS,
     'Federal Statute-U.S. Emblems/Insignias'),
    (FEDERAL_STATUTES_FOREIGN_RELATIONS, 'Federal Statutes-Foreign Relations'),
    (FEDERAL_STATUTES_BANK_AND_BANKING, 'Federal Statutes-Bank and Banking'),
    (FEDERAL_STATUTES_MONEY_AND_FINANCE, 'Federal Statutes-Money and Finance'),
    (FEDERAL_STATUTES_PUBLIC_HEALTH_AND_WELFARE,
     'Federal Statutes-Public Health & Welfare'),
    (FEDERAL_STATUTE_CENSUS, 'Federal Statute-Census'),
    (COMMUNICATION_ACTS_INCLUDING_WIRE_TAPPING,
     'Communication Acts (Including Wire Tapping)'),
    (WIRE_INTERCEPTION, 'Wire Interception'),
    (FEDERAL_STATUTES_COPYRIGHT_LAWS, 'Federal Statutes-Copyright Laws'),
    (FEDERAL_STATUTES_COAST_GUARD, 'Federal Statutes-Coast Guard'),
    (FEDERAL_STATUTES_COMMERCE_AND_TRADE,
     'Federal Statutes-Commerce And Trade'),
    (FEDERAL_STATUTES_CONSUMER_CREDIT_PROTECTION,
     'Federal Statutes-Consumer Credit Protection'),
    (FEDERAL_STATUTES_CONSUMER_PRODUCT_SAFETY,
     'Federal Statutes-Consumer Product Safety'),
    (FEDERAL_STATUES_TOXIC_SUBSTANCE_CONTROL,
     'Federal Statues-Toxic Substance Control'),
    (FEDERAL_STATUTES_TITLE_5, 'Federal Statutes-Title 5'),
    (FEDERAL_STATUTES_CONSERVATION_ACTS, 'Federal Statutes-Conservation Acts'),
    (CONTEMPT, 'Contempt'),
    (CONTEMPT_CONGRESSIONAL, 'Contempt, Congressional'),
    (FORFEITURE_CRIMINAL_OR_DRUG_RELATED,
     'Forfeiture - Criminal or Drug Related'),
    (FEDERAL_STATUTES_EXTORT_OPPRESS_UNDER_LAW,
     'Federal Statutes-Extort/Oppress under Law'),
    (FEDERAL_STATUTES_REMOVAL_FROM_STATE_COURT,
     'Federal Statutes-Removal from State Court'),
    (FEDERAL_STATUTES_LABOR_LAWS, 'Federal Statutes-Labor Laws'),
    (FEDERAL_STATUTES_MINERALS_AND_LAND_MINING,
     'Federal Statutes-Minerals & Land Mining'),
    (CUSTOMS_LAWS_EXCEPT_NARCOTICS_AND_LIQUOR,
     'Customs Laws (Except Narcotics & Liquor)'),
    (CUSTOMS_LAWS_IMPORT_INJURIOUS_ANIMALS,
     'Customs Laws - Import Injurious Animals'),
    (PATENTS_AND_TRADEMARKS, 'Patents and Trademarks'),
    (PATRIOTIC_SOCIETIES_AND_OBSERVANCES,
     'Patriotic Societies And Observances'),
    (VETERANS_BENEFITS, 'Veterans Benefits'),
    (SOCIAL_SECURITY_9940, 'Social Security'),
    (CONNALLY_ACT_HOT_OIL_ACT, 'Connally Act/Hot Oil Act'),
    (TRANSPORT_CONVICT_MADE_GOODS_INTERSTATE,
     'Transport Convict-Made Goods Interstate'),
    (RAILROAD_AND_TRANSPORTATION_ACTS, 'Railroad & Transportation Acts'),
    (DESTRUCTION_OF_PROPERTY_INTERSTATE_COMMERCE,
     'Destruction of Property, Interstate Commerce'),
    (TELEPHONES_TELEGRAPHS_AND_RADIOS, 'Telephones Telegraphs & Radios'),
    (FEDERAL_STATUTE_TRANSPORTATION, 'Federal Statute-Transportation'),
    (WAR_AND_NATIONAL_DEFENSE_OTHER, 'War and National Defense, Other'),
    (TRANSPORTATION_OF_STRIKEBREAKERS, 'Transportation of Strikebreakers'),
    (TAFT_HARTLEY_ACT, 'Taft Hartley Act'),
    (EIGHT_HOUR_DAY_ON_PUBLIC_WORKS, 'Eight Hour Day on Public Works'),
    (PEONAGE, 'Peonage'),
    (FEDERAL_STATUTE_PHW, 'Federal Statute, Phw'),
    (TERRORIST_ACTIVITY, 'Terrorist Activity'),
    (LIQUOR_EXCEPT_INTERNAL_REVENUE, 'Liquor (Except Internal Revenue)'),
    (MARITIME_AND_SHIPPING_LAWS, 'Maritime & Shipping Laws'),
    (STOWAWAYS, 'Stowaways'),
    (FEDERAL_BOAT_SAFETY_ACT_OF_1971, 'Federal Boat Safety Act of 1971'),
    (FEDERAL_WATER_POLLUTION_CONTROL_ACT,
     'Federal Water Pollution Control Act'),
    (POSTAL_NON_MAILABLE_MATERIAL, 'Postal, Non Mailable Material'),
    (POSTAL_INJURY_TO_PROPERTY, 'Postal, Injury to Property'),
    (POSTAL_OBSTRUCTING_THE_MAIL, 'Postal, Obstructing the Mail'),
    (POSTAL_VIOLATIONS_BY_POSTAL_EMPLOYEES,
     'Postal, Violations By Postal Employees'),
    (POSTAL_OTHER, 'Postal, Other'),
    (NATIONAL_PARK_RECREATION_VIOLATIONS_9990,
     'National Park/Recreation Violations'),
    (DESTROYING_FEDERAL_PROPERTY, 'Destroying Federal Property'),
    (INTIMIDATION_OF_WITNESSES_JURORS_ETC,
     'Intimidation of Witnesses, Jurors, etc.'),
    (AIRCRAFT_REGULATIONS, 'Aircraft Regulations'),
    (EXPLOSIVES_EXCEPT_ON_VESSELS, 'Explosives (Except on Vessels)'),
    (GOLD_ACTS, 'Gold Acts'),
    (TRAIN_WRECKING, 'Train Wrecking'),
    (FEDERAL_STATUTES_OTHER, 'Federal Statutes, Other'),
)

# This is a partial list of court timezones. It mostly covers the federal courts
# and in some cases (noted below) it makes decisions about which timezone to use
# for a court that spans multiple timezones. In those cases, we attempt to use
# the timezone with the most people (roughly).
COURT_TIMEZONES = {
    u'akb': 'US/Alaska',
    u'akd': 'US/Alaska',
    u'ald': 'US/Central',
    u'almb': 'US/Central',
    u'almd': 'US/Central',
    u'alnb': 'US/Central',
    u'alnd': 'US/Central',
    u'alsb': 'US/Central',
    u'alsd': 'US/Central',
    u'arb': 'US/Arizona',
    u'areb': 'US/Central',
    u'ared': 'US/Central',
    u'arwb': 'US/Central',
    u'arwd': 'US/Central',
    u'azd': 'US/Arizona',
    u'ca1': 'US/Eastern',
    u'ca10': 'US/Mountain',
    u'ca11': 'US/Eastern',
    u'ca2': 'US/Eastern',
    u'ca3': 'US/Eastern',
    u'ca4': 'US/Eastern',
    u'ca5': 'US/Central',
    u'ca6': 'US/Eastern',
    u'ca7': 'US/Central',
    u'ca8': 'US/Central',
    u'ca9': 'US/Pacific',
    u'caca': 'US/Pacific',
    u'cacb': 'US/Pacific',
    u'cacd': 'US/Pacific',
    u'cadc': 'US/Eastern',
    u'caeb': 'US/Pacific',
    u'caed': 'US/Pacific',
    u'cafc': 'US/Eastern',
    u'californiad': 'US/Pacific',
    u'canalzoned': 'US/Pacific',
    u'canb': 'US/Pacific',
    u'cand': 'US/Pacific',
    u'casb': 'US/Pacific',
    u'casd': 'US/Pacific',
    u'cit': 'US/Eastern',
    u'cob': 'US/Mountain',
    u'cod': 'US/Mountain',
    u'ctb': 'US/Eastern',
    u'ctd': 'US/Eastern',
    u'dcb': 'US/Eastern',
    u'dcd': 'US/Eastern',
    u'deb': 'US/Eastern',
    u'ded': 'US/Eastern',
    u'fld': 'US/Eastern',
    u'flmb': 'US/Eastern',
    u'flmd': 'US/Eastern',
    # some offices flnd are in US/Central (e.g. Pensacola, Panama City)
    # http://www.flsd.uscourts.gov/?page_id=7850
    u'flnb': 'US/Eastern',
    u'flnd': 'US/Eastern',
    u'flsb': 'US/Eastern',
    u'flsd': 'US/Eastern',
    u'gad': 'US/Eastern',
    u'gamb': 'US/Eastern',
    u'gamd': 'US/Eastern',
    u'ganb': 'US/Eastern',
    u'gand': 'US/Eastern',
    u'gasb': 'US/Eastern',
    u'gasd': 'US/Eastern',
    u'gub': 'Pacific/Guam',
    u'gud': 'Pacific/Guam',
    u'hib': 'US/Hawaii',
    u'hid': 'US/Hawaii',
    u'iad': 'US/Central',
    u'ianb': 'US/Central',
    u'iand': 'US/Central',
    u'iasb': 'US/Central',
    u'iasd': 'US/Central',
    u'idb': 'America/Boise',
    u'idd': 'America/Boise',
    u'ilcb': 'US/Central',
    u'ilcd': 'US/Central',
    u'illinoisd': 'US/Central',
    u'illinoised': 'US/Central',
    u'ilnb': 'US/Central',
    u'ilnd': 'US/Central',
    u'ilsb': 'US/Central',
    u'ilsd': 'US/Central',
    u'indianad': 'US/Eastern',
    u'innb': 'US/Eastern',
    u'innd': 'US/Eastern',
    u'insb': 'US/Eastern',
    u'insd': 'US/Eastern',
    u'ksb': 'US/Central',
    u'ksd': 'US/Central',
    u'kyd': 'US/Eastern',
    u'kyeb': 'US/Eastern',
    u'kyed': 'US/Eastern',
    u'kywb': 'US/Eastern',
    u'kywd': 'US/Eastern',
    u'lad': 'US/Central',
    u'laeb': 'US/Central',
    u'laed': 'US/Central',
    u'lamb': 'US/Central',
    u'lamd': 'US/Central',
    u'lawb': 'US/Central',
    u'lawd': 'US/Central',
    u'mab': 'US/Eastern',
    u'mad': 'US/Eastern',
    u'mdb': 'US/Eastern',
    u'mdd': 'US/Eastern',
    u'meb': 'US/Eastern',
    u'med': 'US/Eastern',
    u'michd': 'US/Michigan',
    u'mieb': 'US/Michigan',
    u'mied': 'US/Michigan',
    u'missd': 'US/Central',
    u'miwb': 'US/Michigan',
    u'miwd': 'US/Michigan',
    u'mnb': 'US/Central',
    u'mnd': 'US/Central',
    u'mod': 'US/Central',
    u'moeb': 'US/Central',
    u'moed': 'US/Central',
    u'mowb': 'US/Central',
    u'mowd': 'US/Central',
    u'msnb': 'US/Central',
    u'msnd': 'US/Central',
    u'mspb': 'US/Eastern',
    u'mssb': 'US/Central',
    u'mssd': 'US/Central',
    u'mtb': 'US/Mountain',
    u'mtd': 'US/Mountain',
    u'ncd': 'US/Eastern',
    u'nceb': 'US/Eastern',
    u'nced': 'US/Eastern',
    u'ncmb': 'US/Eastern',
    u'ncmd': 'US/Eastern',
    u'ncwb': 'US/Eastern',
    u'ncwd': 'US/Eastern',
    u'ndb': 'US/Central',
    u'ndd': 'US/Central',
    u'nebraskab': 'US/Central',
    u'ned': 'US/Central',
    u'nhb': 'US/Eastern',
    u'nhd': 'US/Eastern',
    u'njb': 'US/Eastern',
    u'njd': 'US/Eastern',
    u'nmb': 'US/Mountain',
    u'nmd': 'US/Mountain',
    u'nmib': 'Pacific/Guam',
    u'nmid': 'Pacific/Guam',
    u'nvb': 'US/Pacific',
    u'nvd': 'US/Pacific',
    u'nyd': 'US/Eastern',
    u'nyeb': 'US/Eastern',
    u'nyed': 'US/Eastern',
    u'nynb': 'US/Eastern',
    u'nynd': 'US/Eastern',
    u'nysb': 'US/Eastern',
    u'nysd': 'US/Eastern',
    u'nywb': 'US/Eastern',
    u'nywd': 'US/Eastern',
    u'ohiod': 'US/Eastern',
    u'ohnb': 'US/Eastern',
    u'ohnd': 'US/Eastern',
    u'ohsb': 'US/Eastern',
    u'ohsd': 'US/Eastern',
    u'okeb': 'US/Central',
    u'oked': 'US/Central',
    u'oknb': 'US/Central',
    u'oknd': 'US/Central',
    u'okwb': 'US/Central',
    u'okwd': 'US/Central',
    u'orb': 'US/Pacific',
    u'ord': 'US/Pacific',
    u'orld': 'US/Central',
    u'paeb': 'US/Eastern',
    u'paed': 'US/Eastern',
    u'pamb': 'US/Eastern',
    u'pamd': 'US/Eastern',
    u'pawb': 'US/Eastern',
    u'pawd': 'US/Eastern',
    u'prb': 'America/Puerto_Rico',
    u'prd': 'America/Puerto_Rico',
    u'rib': 'US/Eastern',
    u'rid': 'US/Eastern',
    u'scb': 'US/Eastern',
    u'scd': 'US/Eastern',
    u'scotus': 'US/Eastern',
    u'sdb': 'US/Central',
    u'sdd': 'US/Central',
    u'tneb': 'US/Eastern',
    u'tned': 'US/Eastern',
    u'tnmb': 'US/Central',
    u'tnmd': 'US/Central',
    u'tnwb': 'US/Central',
    u'tnwd': 'US/Central',
    u'txeb': 'US/Central',
    u'txed': 'US/Central',
    u'txnb': 'US/Central',
    u'txnd': 'US/Central',
    u'txsb': 'US/Central',
    u'txsd': 'US/Central',
    # Some offices of txwd are in US/Mountain (e.g. El Paso)
    u'txwb': 'US/Central',
    u'txwd': 'US/Central',
    u'uscfc': 'US/Eastern',
    u'utb': 'US/Mountain',
    u'utd': 'US/Mountain',
    u'vad': 'US/Eastern',
    u'vaeb': 'US/Eastern',
    u'vaed': 'US/Eastern',
    u'vawb': 'US/Eastern',
    u'vawd': 'US/Eastern',
    u'vib': 'America/St_Thomas',
    u'vid': 'America/St_Thomas',
    u'vtb': 'US/Eastern',
    u'vtd': 'US/Eastern',
    u'waeb': 'US/Pacific',
    u'waed': 'US/Pacific',
    u'washd': 'US/Pacific',
    u'wawb': 'US/Pacific',
    u'wawd': 'US/Pacific',
    u'wieb': 'US/Central',
    u'wied': 'US/Central',
    u'wisd': 'US/Central',
    u'wiwb': 'US/Central',
    u'wiwd': 'US/Central',
    u'wvad': 'US/Eastern',
    u'wvnb': 'US/Eastern',
    u'wvnd': 'US/Eastern',
    u'wvsb': 'US/Eastern',
    u'wvsd': 'US/Eastern',
    u'wyb': 'US/Mountain',
    u'wyd': 'US/Mountain',
}
