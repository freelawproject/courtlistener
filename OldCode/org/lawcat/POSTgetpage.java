// This software and any associated files are copyright 2010 Brian Carver, 
// Michael Lissner and Longhao Wang.
// 
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
// 
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
// 
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.


package org.lawcat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLConnection;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;

public class POSTgetpage {
	public static String run(String pageURL, String data){
		String content = "";
		
		//URL of the page to scrape; for POST, must be combined with POST parameters
		URL u;
		try {
			u = new URL(pageURL);

			Date today = new Date();
			Calendar c = new GregorianCalendar();
			BufferedReader  br;
			c.setTime(today);
			c.add(Calendar.DATE, -30);
			String m2 = new SimpleDateFormat("MM").format(c.getTime());
			String y2 = new SimpleDateFormat("yyyy").format(c.getTime());
			String d2 = new SimpleDateFormat("dd").format(c.getTime());
	
			
			URLConnection conn = u.openConnection();
			conn.setConnectTimeout(10000);
			conn.setReadTimeout(10000);
			conn.setDoOutput(true);
			OutputStreamWriter wr = new OutputStreamWriter(conn.getOutputStream());
			
			//POST parameters, name and value of parameters comes from the FORM of http://www.ca2.uscourts.gov/opinions.htm
			wr.write("IW_DATABASE=OPN&IW_FIELD_TEXT=*&IW_FILTER_DATE_AFTER=" + y2 + m2 + d2 + "&IW_BATCHSIZE=20&IW_SORT=-DATE");
			wr.flush();
			
			br = new BufferedReader(new InputStreamReader(conn.getInputStream()));
	
			
			String line;
			while ((line = br.readLine()) != null) {
				content += line;
			}

		} catch (Exception e) {
			
			e.printStackTrace();
		}
		return content;
	}
}
