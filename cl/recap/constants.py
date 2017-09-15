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
FAIR_LABOR_STANDARDS_ACT = 710
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
    (PRISONER_PETITIONS_VACATE_SENTENCE, 'Prisoner petitions - vacate sentence'),
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
    (FAIR_LABOR_STANDARDS_ACT, 'Fair Labor Standards Act'),
    (LABOR_MANAGEMENT_RELATIONS_ACT, 'Labor/Management Relations Act'),
    (LABOR_MANAGEMENT_REPORT_DISCLOSURE, 'Labor/Management report & disclosure'),
    (RAILWAY_LABOR_ACT, 'Railway Labor Act'),
    (FAMILY_AND_MEDICAL_LEAVE_ACT, 'Family and Medical Leave Act'),
    (LABOR_LITIGATION_OTHER, 'Other labor litigation'),
    (EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT, 'Employee Retirement Income '
                                              'Security Act'),
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
    (APPEAL_OF_FEE_EQUAL_ACCESS_TO_JUSTICE, 'Appeal of fee - equal access to '
                                            'justice'),
    (DOMESTIC_RELATIONS, 'Domestic relations'),
    (INSANITY, 'Insanity'),
    (PROBATE, 'Probate'),
    (SUBSTITUTE_TRUSTEE, 'Substitute trustee'),
    (CONSTITUTIONALITY_OF_STATE_STATUTES, 'Constitutionality of state statutes'),
    (OTHER, 'Other'),
    (LOCAL_JURISDICTIONAL_APPEAL, 'Local jurisdictional appeal'),
    (MISCELLANEOUS, 'Miscellaneous'),
)


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

idb_field_mappings = {
    'CIRCUIT': "circuit",
    'DISTRICT': 'district',
    'OFFICE': 'office',
    'DOCKET': 'docket_number',
    'ORIGIN': 'origin',
    'FILEDATE': 'date_filed',
    'JURIS': 'jurisdiction',
    'NOS': 'nature_of_suit',
    'TITLE': 'title',
    'SECTION': 'section',
    'SUBSECTION': 'subsection',
    'RESIDENC': 'diversity_of_residence',
    'CLASSACT': 'class_action',
    'DEMANDED': 'monetary_demand',
    'COUNTY': 'county_of_residence',
    'ARBIT': 'arbitration_at_filing',
    'MDLDOCK': 'multidistrict_litigation_docket_number',
    'PLT': 'plaintiff',
    'DEF': 'defendant',
    'TRANSDAT': 'date_transfer',
    'TRANSOFF': 'transfer_office',
    'TRANSDOC': 'transfer_docket_number',
    'TRANSORG': 'transfer_origin',
    'TERMDATE': 'date_terminated',
    'TRCLACT': 'termination_class_action_status',
    'PROCPROG': 'procedural_progress',
    'DISP': 'disposition',
    'NOJ': 'nature_of_judgement',
    'AMTREC': 'amount_received',
    'JUDGMENT': 'judgment',
    'PROSE': 'pro_se',
    'TAPEYEAR': 'year_of_tape',
}
