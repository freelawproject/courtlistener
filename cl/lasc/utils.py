def make_case_id(case_data):
    """Make a semicolon separated LASC case_id"""
    docket_number = case_data['Docket']['docket_number']
    district = case_data['Docket']['district']
    division_code = case_data['Docket']['division_code']
    return ";".join([docket_number, district, division_code])
