# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.




"""The emailer essentially has to do a couple of things:
 1. It should be triggerable via a URL at /email/daily/, /email/weekly/, and /email/monthly/
    1.1. These URLs will be hit on everyday, Sundays, and the 1st of each month via cron. 
 2. After being triggered, it should do the following:
    - for each user, build an email.
        - for their daily alerts, do a search for that alert, checking for new cases within the last day.
        - for their weekly alert, do a search for that alert, checking for new cases within the last week.
        - for their monthly alert, do a search for that alert, checking for new cases within the last month.
            - if there is a hit for that alert/user add it to a queue
        - Once all of their alerts have been checked, send the email, and proceed to the next user.
 3. A better method is needed that only iterates over the daily/weekly/monthly alerts on a given day/week/month.
    - So, for a daily/weekly/monthly URL, we begin by querying all the daily/weekly/monthly alerts
        - For each alert, we see if there are any new hits
                - If there is a hit, we pull the user associated with the alert, and generate an email""" 
        
        
def emailer(request, rate):
    """This will load all the users each day/week/month, and send them emails."""
    pass
    
    
     
