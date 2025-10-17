F_EXAMPLES = """
- "no. 8,' -> ['8']
- 'Case Nos. 15 - 3751_1, et al.' -> ['15-3751']
- 'Docket 08-1886-cr (L)' -> ['08-1886-cr']
- 'Civil Case No. 16-157 (RMC)' -> ['16-157']
- 'Case No. 10-CV-976 (CRC)' -> ['10-cv-976']
- '1197, Docket 91-9325(L)' -> ['91-9325']
- 'No. 424, Docket 5245' -> ['5245']
- 'No. 235, Docket 12-3265' -> ['12-3265']
- '424, Docket 5245' -> ['5245']
- '235, Dockets 12-3265/3266' -> ['12-3265', '12-3266']
- 'Cal. 1360, Docket 84-1088' -> ['84-1088']
- '94-70183; Tax Court 16266-91' -> ['94-70183', '16266-91']
- '80-5569; Bankruptcy 79-03326-M' -> ['80-5569', '79-03326-m']
- '05-11019; D.C. Docket 04-00102-CV-2' -> ['05-11019', '04-00102-cv-2']
- '05-11125; BIA A96-442-100' -> ['05-11125', 'A96-442-100']
- '5733, 5734' -> ['5733', '5734']
- 'CASES. 05-6654-cr(L), 06-1202-cv' -> ['05-6654-cr', '06-1202-cv']
- '10-3359-ag (Lead) & 10-3615-ag (XAP)' -> ['10-3359-ag', '10-3615-ag']
- '922 to 925, Sockets 1313, 1315, and 1318' -> ['1313', '1315', '1318']
- '05-16173, 05-16389. Adv. No. 98-2313-RCJ' -> ['05-16173', '05-16389', '98-2313-rcj']
- 'No. 11845 (11,850)' -> ['11845', '11850']
- 'Nos. 1,350,1,351' -> ['1350', '1351']
- '85-1150/1171, 89-1208/ 1209' -> ['85-1150', '85-1171', '89-1208', '89-1209']
- 'Case nos. 13-4145/ 14-3816/ 15-3462' -> ['13-4145', '14-3816', '15-3462']
- '05-11847/11848; Agency A95-886-023 & A95-886-024' -> ['05-11847', '05-11848', 'A95-886-023', 'A95-886-024']
- '17-1222; 1250' -> ['17-1222', '17-1250']
- '1222-1224_2' -> ['1222', '1223', '1224']
- 'Nos. 258, 259 and 260, Dockets 80-7436, 7438 and 7446' -> ['80-7436', '80-7438', '80-7446']
- 'Nos. 5399, 5400, 5412-5414' -> ['5399', '5400', '5412', '5413', '5414']
- 'No. 4819, C/with Nos. 4820-4824 except 4823' -> ['4819', '4820', '4821', '4822', '4824']
- '75-1471 — 75-1474' -> ['75-1471', '75-1472', '75-1473', '75-1474']
- 'Nos. 16-5149 thru 5152' -> ['16-5149', '16-5150', '16-5151', '16-5152']
- '79-1261-3' -> ['79-1261', '79-1262', '79-1263']
- '12-1234-1236 August Term, 2012' -> ['12-1234', '12-1235', '12-1236']
- 'Docket A-1234 (12A34)' -> ['A-1234', '12A34']
- 'NOS. 11-2164 (D-5678) & 12D32' -> ['11-2164', 'D-5678', '12D32']
- 'No. M-71_1 ; 72M56 (O. T. 1997)' -> ['M-71', '72M56']
- 'Case D-5678 and 22-1234' -> ['D-5678', '22-1234']
- '79-1261-3' -> ['79-1261', '79-1262', '79-1263']
- 'No.  88-6857 (A-746); No. A-758 (88-6861)' -> ['88-6857', 'A-746', 'A-758', '88-6861']
- 'No. 355, MISC ' -> ['355, Misc.']
- '123 M' -> ['123, Misc.']
- 'Cases: 1234; 941, Misc , 945, miscellaneous' -> ['1234', '941, Misc.', '945, Misc.']
- ' No. 142, Original.' -> ['142, Orig.']
- '940, 941, ORIG.' -> ['940, Orig.', '941, Orig.']
- '61 original and 672' -> ['61, Orig.', '672']
- 'Nos. 78-5134-5-41-2-3 and 78-5074' -> ['78-5134', '78-5135', '78-5141', '78-5142', '78-5143', '78-5074']
- 'Case No. 1:18-CV-00518 (TNM) Criminal No.:  10-CR-1929 (BJR)' -> ['1:18-cv-00518', '10-cr-1929']
- 'Patent Appeal. No. 1743' -> ['1743']
- '05-125 NAC' -> ['05-125']
- 'Civil Action No. 15-----1391 (ABJ) AND Misc. 855' -> ['15-1391', '855, Misc.']
- 'BOCKET. CIV.A.04-526 HHK/JMF & CASE.: 10-FS-124 AND Case No. 16-mc-2581 (RC/GMH)' -> ['04-526', '10-fs-124', '16-mc-2581']
- (District Court No. 80-3684 and related District Court Nos. 80-4016, 81-951 and 81-3616.) No. 84-3695 -> ['80-3684', '80-4016', '81-951', '81-3616', '84-3695']
- 'Nos. 85-5263/5378, 85-5412' -> ['85-5263', '85-5378', '85-5412']
"""

F_GENERAL_GUIDELINES = """
1. Remove any leading 'No.', 'Nos.', 'No', 'Case No.', 'Case No', 'Docket No.', 'Docket No', 'Docket', 'Case', or similar prefixes.
2. Remove any leading or trailing whitespaces, periods, underscores, words, or phrases.
3. If dash is used as a separator, standardize it as a single hyphen ('-').
4. If the docket number ends in "Misc.", "Misc", " M" or any other variation that implies it's a miscellaneous docket number, standardize it to "NNNN, Misc." where 'NNNN' is the docket number sequence of 1 to 6 digits.
5. If the docket number ends in "Orig.", "Orig", "Original" or any other variation that implies it's an original docket number, standardize it to "NNNN, Orig." where 'NNNN' is the docket number sequence of 1 to 6 digits.
6. Docket number formatted as "NNMNN" or "NNANN" or "NNDNN" where "M" or "A" or "D" is a letter separator and "NN" is a sequence of 1 to 6 digits, or any other format similar to this, should be kept as is.
7. Docket number formatted as "D-NNNN" or "A-NNNN" where "D" or "A" is a letter prefix/separator and "NNNN" is a sequence of 1 to 6 digits, or any other format similar to this, should be kept as is.
8. If the word “Docket” or “Dockets” appears in the middle of the string, ignore and exclude all numbers that occur before it. Only extract numbers that occur after 'Docket' or 'Dockets'. Any number before 'Docket' or 'Dockets' must never be treated as a docket number.
9. Unless special instructions are provided, do not change the format of a docket number to another format. Letters, dashes, and numbers within the docket number should be preserved without modification, omission, or addition.
"""

OUTPUT_FORMAT = """
Output should be a json array of objects, each with the following keys:
- unique_id: The unique identifier for the case.
- cleaned_nums: An array of cleaned and standardized docket numbers. If no docket numbers can be extracted, return an empty array.
"""


F_PROMPT = f"""
You are an expert assistant that cleans and standardizes legal case docket numbers.

You will receive an array of json with unique_id as key and docket number string as value, the docket number string may contain one or more docket numbers.
Your task is to extract and standardize each docket number. You are to then output an array of json objects, each with the unique_id and cleaned_nums keys.
You should followed the general cleaning guidelines and refer to the examples when cleaning and standardizing the docket numbers, however, the examples are not exhaustive, you should use your judgment and expertise to handle any edge cases or variations.

## General Cleaning Guidelines:
{F_GENERAL_GUIDELINES}

## Output Format:
{OUTPUT_FORMAT}

## Examples:
{F_EXAMPLES}
"""


F_TIE_BREAKER = f"""
You are an expert assistant that cleans and standardizes legal case docket numbers.

You will receive an array of json with unique_id as key and docket_number string as value, the docket_number string may contain one or more docket numbers.
The array will also contain the initial cleaned results from two previous attempts. Your task is to review the initial cleaned results against the guidelines and examples and select from the previous attempts the one that best adheres to the guidelines and examples.
If neither of the previous attempts are satisfactory, you should clean and standardize the docket numbers yourself. You are to then output an array of json objects, each with the unique_id and cleaned_nums keys.

You should follow the general cleaning guidelines and refer to the examples when cleaning and standardizing the docket numbers, however, the examples are not exhaustive, you should use your judgment and expertise to handle any edge cases or variations.
You should pay special attention to the special cleaning guidelines as it emphasizes certain aspects that the previous attempts may have overlooked.

## General Cleaning Guidelines:
{F_GENERAL_GUIDELINES}

## Special Cleaning Guidelines:
- When dealing with docket numbers with the word "Docket" or "Dockets" in the middle of the string, be sure to remove any numbers before it, only the values after "Docket" or "Dockets" should be considered docket numbers. For example, "Nos. 258, 259 and 260, Dockets 80-7436, 7438 and 7446" should be cleaned to ["80-7436", "80-7438", "80-7446"] and "424, Docket 5245" should be cleaned to ["5245"].
- Docket numbers separated by slashes (/) may need to be expanded. For example, "85-5263/5378" should be expanded to ["85-5263", "85-5378"].
- Do not confuse slashes (/) used as separators with dashes (-) used to indicate ranges. For example, "85-1150/1171" should be expanded to ["85-1150", "85-1171"], while "75-1471 — 75-1474" should be expanded to ["75-1471", "75-1472", "75-1473", "75-1474"].
- Do not remove prefixes or suffixes unless specified in the general cleaning guidelines or examples. For example, "No. 99-50648; D.C. No. CR-99-00724-RMB (L)" should be cleaned to ["99-50648", "CR-99-00724-RMB"].

## Output Format:
{OUTPUT_FORMAT}

## Examples:
{F_EXAMPLES}
"""
