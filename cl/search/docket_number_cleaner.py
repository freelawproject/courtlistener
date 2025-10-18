import logging
import re

from django.conf import settings
from django.utils import timezone
from pydantic import ValidationError
from sentry_sdk import capture_exception

from cl.lib.llm import call_llm
from cl.lib.string_utils import normalize_dashes
from cl.search.llm_models import CleanDocketNumber
from cl.search.llm_prompts import F_PROMPT, F_TIE_BREAKER
from cl.search.models import Court, Docket

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

court_map = {
    "scotus": Court.FEDERAL_APPELLATE,
    "cadc": Court.FEDERAL_APPELLATE,
    "ca1": Court.FEDERAL_APPELLATE,
    "ca2": Court.FEDERAL_APPELLATE,
    "ca3": Court.FEDERAL_APPELLATE,
    "ca4": Court.FEDERAL_APPELLATE,
    "ca5": Court.FEDERAL_APPELLATE,
    "ca6": Court.FEDERAL_APPELLATE,
    "ca7": Court.FEDERAL_APPELLATE,
    "ca8": Court.FEDERAL_APPELLATE,
    "ca9": Court.FEDERAL_APPELLATE,
    "ca10": Court.FEDERAL_APPELLATE,
    "ca11": Court.FEDERAL_APPELLATE,
}

generic_patterns = {
    Court.FEDERAL_APPELLATE: [
        r"\d{1,2}-\d{1,6}-[a-zA-Z]{2}",  # e.g., 12-1234-ag, 12-1234-pr
        r"\d{1,2}-\d{1,6}[a-zA-Z]{1}",  # e.g., 12-1234P, 12-1234U
        r"\d{1,2}[a-zA-Z]{1}\d{1,6}",  # e.g., 12A1234, 12M1234
        r"[a-zA-Z]{1}-\d{1,6}",  # e.g., A-1234, D-1234
        r"\d{1,2}-\d{1,6}",  # e.g., 12-1234
        r"\d{1,6}",  # e.g., 1234
    ]
}

system_prompts = {Court.FEDERAL_APPELLATE: F_PROMPT}
tie_breaker_prompts = {Court.FEDERAL_APPELLATE: F_TIE_BREAKER}


def get_clean_methods(court_type: str) -> tuple:
    """
    Returns cleaning methods for docket numbers based on the court type.

    :param court_type: The type of court, used to determine which cleaning methods to return.
    :return: A tuple containing two functions for cleaning docket numbers corresponding to the given court type.
               If the court type is not recognized, returns (None, None).
    """
    match court_type.lower():
        case "f":
            return prelim_clean_F, regex_clean_F
        case _:
            return None, None


def is_generic(s: str, court_map: str) -> bool:
    """
    Determines if the given string `s` matches any generic pattern associated with the specified `court_map`.

    :param s: The string to check against the generic patterns.
    :param court_map: The key used to retrieve the list of generic patterns from `generic_patterns`.
    :return: True if `s` matches any pattern for the given `court_map`, False otherwise.
    """
    patterns = generic_patterns.get(court_map, [])
    if any(re.fullmatch(p, s) for p in patterns):
        return True
    return False


def prelim_clean_F(s: str) -> str:
    """
    Cleans and normalizes federal appellate docket numbers.

    Steps:
    - Normalize dash characters.
    - Remove spaces around dashes.
    - Trim whitespace.
    - Remove trailing numbers after underscores.
    - Remove leading/trailing dashes and periods.
    - Remove common docket/case number prefixes.

    :param s: The input docket number string.
    :return: The cleaned and normalized docket number string.
    """
    s = normalize_dashes(s)
    s = s.strip()
    s = re.sub(r"\s*-\s*", "-", s)  # Remove spaces around dashes
    s = re.sub(r"_\d+$", "", s)  # Remove trailing numbers after underscores
    s = re.sub(r"^-+|-+$", "", s)  # Remove leading/trailing dashes
    s = re.sub(r"\.+$", "", s)  # Remove trailing periods
    s = re.sub(
        r"^(?:No\.?|Case No\.?|Docket No\.?|Docket|Case)\s+",
        "",
        s,
        flags=re.IGNORECASE,
    )  # Remove common prefixes
    return s


def regex_clean_F(s: str) -> str:
    """
    Cleans and normalizes federal appellate docket numbers from a given string.

    :param s: The input string containing raw federal appellate docket numbers.
    :return: A semicolon-separated string of cleaned and normalized docket numbers in uppercase.
    """
    # All patterns to match
    patterns = generic_patterns.get(Court.FEDERAL_APPELLATE, [])
    # Combine patterns into one regex
    combined_pattern = "|".join(patterns)
    candidates = re.findall(combined_pattern, s, flags=re.IGNORECASE)
    cleaned = []
    for c in candidates:
        # 1. Handle patterns with dash and suffix (e.g., 12-1234-ag)
        m = re.match(
            r"(\d{1,2})-(\d{1,6})-([a-zA-Z]{2})", c, flags=re.IGNORECASE
        )
        if m:
            yy, nnnn, suffix = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}-{suffix}")
            continue
        # 2. Handle patterns with dash and single-letter suffix (e.g., 12-1234P)
        m = re.match(
            r"(\d{1,2})-(\d{1,6})([a-zA-Z]{1})$", c, flags=re.IGNORECASE
        )
        if m:
            yy, nnnn, suffix = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}{suffix}")
            continue
        # 3. Handle patterns like 12-1234
        m = re.match(r"(\d{1,2})-(\d{1,6})$", c, flags=re.IGNORECASE)
        if m:
            yy, nnnn = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}")
            continue
        # 4. Handle patterns like 12A1234 or 12M1234
        m = re.match(
            r"(\d{1,2})([a-zA-Z]{1})(\d{1,6})", c, flags=re.IGNORECASE
        )
        if m:
            yy, letter, nnnn = m.groups()
            cleaned.append(f"{yy.zfill(2)}{letter}{nnnn}")
            continue
        # 5. Handle patterns like A-1234 or D-1234
        m = re.match(r"([a-zA-Z]{1})-(\d{1,6})", c, flags=re.IGNORECASE)
        if m:
            letter, nnnn = m.groups()
            cleaned.append(f"{letter}-{nnnn}")
            continue
        # 6. Handle just numbers
        m = re.match(r"^\d{1,6}$", c, flags=re.IGNORECASE)
        if m:
            cleaned.append(str(int(c)))
            continue

    cleaned = [s.upper() for s in cleaned]
    return "; ".join(cleaned)


def clean_docket_number_raw(
    docket_id: int, docket_number_raw: str, court_id: str
) -> tuple[str, int | None]:
    """
    Cleans a raw docket number string based on the court's specific cleaning logic and identifies those that need LLM cleaning.

    :param docket_id: The unique identifier for the docket.
    :param docket_number_raw: The raw docket number string to be cleaned.
    :param court_id: The identifier for the court, used to select cleaning logic.
    :return: A tuple containing the cleaned docket number and the docket_id for downstream LLM processing, if applicable.
    """
    court_type = court_map.get(court_id)

    if court_type:
        prelim_func, regex_func = get_clean_methods(court_type)

        if prelim_func:
            prelim_cleaned = prelim_func(docket_number_raw)
            if is_generic(prelim_cleaned, court_type):
                if regex_func:
                    docket_number = regex_func(prelim_cleaned)
                    return docket_number, None
            else:
                return docket_number_raw, docket_id

    return docket_number_raw, None


def get_docket(docket_id: int) -> Docket | None:
    """
    Retrieve a Docket object by its ID.

    :param docket_id: The primary key ID of the Docket to retrieve.
    :return: The Docket object if found, otherwise None.
    """
    try:
        docket_obj = Docket.objects.filter(id=docket_id).first()
        return docket_obj
    except Docket.DoesNotExist:
        logger.error(f"Docket with id {docket_id} does not exist.")
        return None


def update_docket_number(
    docket_id: int, docket_number: str, start_timestamp: timezone.datetime
) -> int | None:
    """
    Update the docket_number field of a Docket object.

    :param docket_id: The primary key ID of the Docket to update.
    :param docket_number: The new docket number to set.
    :return: docket_id if the docket_number was updated, otherwise None.
    """
    docket = get_docket(docket_id)
    if docket:
        last_update_timestamp = docket.date_modified
        # only update if the docket was not modified since the start of the llm cleaning process
        if last_update_timestamp < start_timestamp:
            docket.docket_number = docket_number
            docket.save(update_fields=["docket_number"])
            return docket_id
        else:
            return None
    else:
        # return the docket_id to be removed from redis cache if the docket was deleted
        return docket_id


def create_llm_court_batches(
    llm_batch: list[int],
) -> dict[str, list[dict[int, str]]]:
    """
    Groups docket numbers by their associated court type for a given batch of docket_ids.

    :param llm_batch: A list of docket_ids to be processed.
    :return: A dictionary where each key is a court mapping (as determined by `court_map`),
              and each value is a list of dictionaries of {docket_id: docket_number_raw}.
    """
    court_batches = {}
    # Group batches by court type
    for docket_id in llm_batch:
        docket_obj = get_docket(docket_id)
        if not docket_obj:
            continue
        court_id, docket_number_raw = (
            docket_obj.court_id,
            docket_obj.docket_number_raw,
        )
        court_mapping = court_map.get(court_id, None)
        if court_mapping not in court_batches:
            court_batches[court_mapping] = []
        court_batches[court_mapping].append({docket_id: docket_number_raw})
    return court_batches


def extract_with_llm(
    batch: list[dict[int, str]], system_prompt: str, model_id: str
) -> dict[int, str] | None:
    """
    Extracts and cleans a batch of docket numbers using a Large Language Model (LLM).

    :param batch: The batch of records to process. Each item is a dictionary with the docket_id (int) as the key and the raw_docket_number (str) as the value.
    :param system_prompt: The system prompt to provide to the LLM.
    :param model_id: The identifier for the LLM model to use.
    :return: A dictionary where keys are unique docket_ids (int) and values are cleaned docket numbers (str).
    """
    try:
        llm_response = call_llm(
            system_prompt=system_prompt,
            user_prompt=f"{batch}",
            model=model_id,
            response_model=CleanDocketNumber,
            temperature=settings.DOCKET_NUMBER_CLEANING_TEMPERATURE,
            max_completion_tokens=settings.DOCKET_NUMBER_CLEANING_MAX_COMPLETION_TOKENS,
            api_key=settings.DOCKET_NUMBER_CLEANING_API_KEY,
        )
    except ValidationError as e:
        logger.error(
            "LLM - Response validation error for batch=%s",
            f"{batch}",
            extra={
                "validation_errors": e.errors(),
                "fingerprint": ["llm-docket-number-validation-error"],
            },
        )
        return
    except Exception as e:
        # Only expect to get instructor exceptions here to track them
        capture_exception(e)
        raise

    if not isinstance(llm_response, CleanDocketNumber):
        # Added this to avoid mypy errors
        logger.error("LLM - Invalid response type: %s", type(llm_response))
        return

    records = {}
    for item in llm_response.docket_numbers:
        docket_id = item.unique_id
        docket_num = [s.upper() for s in sorted(list(set(item.cleaned_nums)))]
        records[int(docket_id)] = "; ".join(docket_num)

    return records


def process_llm_batches(
    llm_batches: list[dict[int, str]],
    system_prompt: str,
    model_id: str,
    retry: int,
    max_retries: int,
    batch_size: int,
    all_cleaned: dict[int, str],
) -> dict[int, str]:
    """
    Processes batches of records using a language model (LLM), recursively retry with smaller batch sizes for failed extractions.

    :param llm_batches: The batch of records to process. Each item is a dictionary with the docket_id (int) as the key and the raw_docket_number (str) as the value.
    :param system_prompt: The system prompt to provide to the LLM.
    :param model_id: Identifier for the LLM model to use.
    :param retry: Current retry attempt count.
    :param max_retries: Maximum number of allowed retries for failed batches.
    :param batch_size: Number of records to process in each batch.
    :param all_cleaned: Accumulator dictionary for all processed records.
    :return: A dictionary mapping record IDs to their cleaned/extracted values, including any unprocessed records after max retries.
    """
    logger.info(f"---Processing {len(llm_batches)} records with {model_id}---")
    batches = [
        llm_batches[i : i + batch_size]
        for i in range(0, len(llm_batches), batch_size)
    ]
    # Process each batch of batch_size
    for batch in batches:
        logger.info(f"Batch size: {len(batch)}")
        parsed_output = extract_with_llm(batch, system_prompt, model_id)
        all_cleaned.update(parsed_output or {})
    # Check for any still-unprocessed records (e.g., if LLM failed to extract)
    processed_ids = [k for k in all_cleaned.keys()]
    remaining = [
        batch
        for batch in llm_batches
        if list(batch.keys())[0] not in processed_ids
    ]
    logger.info(f"---{len(remaining)} remaining---")
    if remaining and retry < max_retries:
        # Recurse on remaining
        logger.info(f"---Retry {retry + 1}---")
        retry += 1
        return process_llm_batches(
            llm_batches=remaining,
            system_prompt=system_prompt,
            model_id=model_id,
            retry=retry,
            max_retries=max_retries,
            batch_size=max(1, int(batch_size / 2)),
            all_cleaned=all_cleaned,
        )
    elif remaining and retry >= max_retries:
        unprocessed_ids = [list(batch.keys())[0] for batch in remaining]
        logger.info(
            f"---Max retries reached. {len(remaining)} unprocessed records assigned raw values: {unprocessed_ids}.---"
        )
        for batch in remaining:
            docket_id = list(batch.keys())[0]
            all_cleaned[docket_id] = batch.get(
                docket_id, ""
            )  # Assign raw if still unprocessed
    return all_cleaned


def call_models_and_compare_results(
    court_batch: list[dict[int, str]],
    court_mapping: str,
    model_one: str,
    model_two: str,
    start_timestamp: timezone.datetime,
) -> tuple[list[dict[int, str]], list[int]]:
    """
    Calls two language models asynchronously to process a batch of court docket numbers,
    compares their results, updates docket numbers when both models agree, and collects batches
    for further processing when they disagree.

    :param court_batch: A list of dictionaries, each mapping docket IDs to raw docket numbers for a batch of court cases.
    :param court_mapping: A key used to retrieve the appropriate system prompt for the court from the system_prompts dictionary.
    :param model_one: The identifier for the first language model to use for processing.
    :param model_two: The identifier for the second language model to use for processing.
    :return: A tuple containing:
             - A list of dictionaries, each containing docket IDs and their corresponding raw docket numbers,
               representing cases where the two models disagreed or returned empty results, to be processed by a larger or fallback model.
             - A list of docket IDs that were successfully updated with cleaned docket numbers.
    """
    next_model_batches = []
    # Call both models
    model_one_results = process_llm_batches(
        llm_batches=court_batch,
        system_prompt=system_prompts.get(court_mapping, ""),
        model_id=model_one,
        retry=0,
        max_retries=settings.DOCKET_NUMBER_CLEANING_LLM_MAX_RETRIES,
        batch_size=settings.DOCKET_NUMBER_CLEANING_LLM_BATCH_SIZE,
        all_cleaned=dict(),
    )
    model_two_results = process_llm_batches(
        llm_batches=court_batch,
        system_prompt=system_prompts.get(court_mapping, ""),
        model_id=model_two,
        retry=0,
        max_retries=settings.DOCKET_NUMBER_CLEANING_LLM_MAX_RETRIES,
        batch_size=settings.DOCKET_NUMBER_CLEANING_LLM_BATCH_SIZE,
        all_cleaned=dict(),
    )

    # Compare results and create batch for prediction with larger model
    processed_dockets = []
    for docket_id, docket_number_one in model_one_results.items():
        docket_number_two = model_two_results.get(docket_id, None)
        if docket_number_one == docket_number_two and docket_number_one != "":
            processed_dockets.append(
                update_docket_number(
                    docket_id, docket_number_one, start_timestamp
                )
            )
        else:
            # Find the raw_docket_number from court_batch using docket_id
            docket_number_raw = None
            for batch in court_batch:
                if docket_id in batch:
                    docket_number_raw = batch[docket_id]
                    break
            if docket_number_raw is not None:
                next_model_batches.append({docket_id: docket_number_raw})
    return next_model_batches, processed_dockets


def llm_clean_docket_numbers(
    llm_batch: list[int],
) -> list[int]:
    """
    Cleans docket numbers for batches of court records using multiple LLM models to reach consensus.

    This function processes each batch of court records by:
    1. Running two lightweight LLM models to clean docket numbers and comparing their results.
    2. For records where the two models disagree, running two full LLM models and comparing their results.
    3. For remaining ties, using a tie-breaker LLM model to finalize the cleaned docket numbers.
    4. Updating the docket numbers in the database with the cleaned results.

    :param llm_batch: A list of docket IDs to be processed.
    :return: A list of docket IDs that were successfully updated with cleaned docket numbers.
    """
    court_batches = create_llm_court_batches(llm_batch)
    processed_llm_batch = []
    # Process each court batch
    for court_mapping, court_batch in court_batches.items():
        logger.info(
            f"Processing court: {court_mapping} with {len(court_batch)} records"
        )

        if court_mapping:
            start_timestamp = timezone.now()
            # First pass with two mini models to find consensus
            next_model_batches, processed_dockets = (
                call_models_and_compare_results(
                    court_batch=court_batch,
                    court_mapping=court_mapping,
                    model_one=settings.DOCKET_NUMBER_CLEANING_MINI_MODEL_ONE,
                    model_two=settings.DOCKET_NUMBER_CLEANING_MINI_MODEL_TWO,
                    start_timestamp=start_timestamp,
                )
            )
            processed_llm_batch.extend(processed_dockets)
            # Next pass with two full models for non-consensus
            if next_model_batches:
                tie_breaker_batches, processed_dockets = (
                    call_models_and_compare_results(
                        court_batch=next_model_batches,
                        court_mapping=court_mapping,
                        model_one=settings.DOCKET_NUMBER_CLEANING_FULL_MODEL_ONE,
                        model_two=settings.DOCKET_NUMBER_CLEANING_FULL_MODEL_TWO,
                        start_timestamp=start_timestamp,
                    )
                )
                processed_llm_batch.extend(processed_dockets)
                # Third pass with tie-breaker model
                if tie_breaker_batches:
                    tie_breaker_results = process_llm_batches(
                        llm_batches=tie_breaker_batches,
                        system_prompt=tie_breaker_prompts.get(
                            court_mapping, ""
                        ),
                        model_id=settings.DOCKET_NUMBER_CLEANING_TIE_BREAKER_MODEL,
                        retry=0,
                        max_retries=settings.DOCKET_NUMBER_CLEANING_LLM_MAX_RETRIES,
                        batch_size=settings.DOCKET_NUMBER_CLEANING_LLM_BATCH_SIZE,
                        all_cleaned=dict(),
                    )
                    for (
                        docket_id,
                        docket_number,
                    ) in tie_breaker_results.items():
                        processed_llm_batch.append(
                            update_docket_number(
                                docket_id, docket_number, start_timestamp
                            )
                        )

    return processed_llm_batch
