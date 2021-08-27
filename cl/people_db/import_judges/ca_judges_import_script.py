from cl.people_db.import_judges.ca_judges_import_helpers import (
    find_court,
    find_or_create_judge,
    get_appointer,
    get_how_selected,
    load_json_file,
)


def import_judges_from_json():
    # load the counties JSON
    counties = load_json_file("ca_counties.json")

    # load the deduped json and returns the judge json
    # i.e., { count: int, judges: { fullName: string, positions: Position }[] }
    judge_json = load_json_file("ca_judges.json")

    count = judge_json["count"]
    judge_info = judge_json["judges"]

    print(f"Processing {count} unique judges")

    for info in judge_info:

        fullname = info["fullName"]
        positions = info["positions"]
        print(f"\n")
        print(f"Processing {fullname}")
        print(f"----------------------")

        judge = find_or_create_judge(info, counties)

        for i, position in enumerate(positions):
            print(f"----------------------")
            print(f"Processing Position #{i}")
            court = find_court(position, counties)

            job_title = position["jobTitle"]
            organization_name = position["orgName"]
            date_start = position["experienceStatusEffectiveDate"]

            # TODO
            # [date_termination, termination_reason] = get_termination_date_and_reason(
            # position
            # )

            position_type = position["judicialPositionJobClass"]

            how_selected = get_how_selected(
                position["judicialExperiencePendingStatus"]
            )

            appointer = get_appointer(
                position["judicialExperiencePendingSubType"]
            )

            print(f"court: {court}")
            print(f"job_title: {job_title}")
            print(f"organization_name: {organization_name}")
            print(f"date_start: {date_start}")
            print(f"position_type: {position_type}")
            print(f"how_selected: {how_selected}")
            print(f"appointer: {appointer}")
            # print(f"date_termination: {date_termination}")
            # print(f"termination_reason: {termination_reason}")

            # new_position = Position(
            #   job_title = job_title
            #   organization_name = organization_name
            #   date_start = date_start
            #   position_type = position_type
            #   how_selected = how_selected
            #   appointer = appointer
            #   date_termination
            # )

            print(f"Successfully created position {job_title}")
