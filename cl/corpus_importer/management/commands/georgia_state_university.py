TAG_NAME = "yDVxdAsAKSixdsoM"
TAG_NAME_OPINIONS = f"{TAG_NAME}-opinions"

"""
This file contains some of the work product of our collaboration with GSU. The
process we went through for this project was:

 - They provided a spreadsheet with case names, jurisdictions, and dates.

 - We took that spreadsheet and looked up anything we could in our IDB DB.

 - That didn't always work, so we provided a spreadsheet of missing values
   back to GSU.

 - Students then completed the missing values, which we merged back into our
   spreadsheet.

 - From there, we used the new spreadsheet to look up the new and old values
   and download them.

 - Once the docket is downloaded, we get the docket entries matching the dates
   on the spreadsheet.

All of this process is summarized in an email dated 2018-04-17.

All code deleted as part of adding type hints. Find it in git.
"""
