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
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLConnection;


public class GetPage {
	public static String readPage2Str(String urlStr){
		String line;
		URL u; 
		InputStream is = null; 
		BufferedReader  br;
		
		try {
			u = new URL(urlStr);
			URLConnection c = u.openConnection();
			c.setConnectTimeout(10000);
			c.setReadTimeout(10000);
			
			try {
				is = c.getInputStream();         // throws an IOException
			}
			catch (FileNotFoundException e) {
				System.out.println("URL not found " + urlStr);
				return "";
			}
			
			br = new BufferedReader(new InputStreamReader(is));
			
			String pageContent = "";

			while ((line = br.readLine()) != null) {
				pageContent += line;
			}

			return pageContent;
		}
		catch (MalformedURLException mue) {

			System.out.println("MalformedURLException"); 
			Log.writeLog("MalformedURLException");

		} catch (IOException ioe) {

			System.out.println("IOException"); 
			Log.writeLog("IOException"); 

		} finally {
			try {
				is.close();
			} catch (IOException e) {
				
				e.printStackTrace();
				Log.writeLog( e.toString() );
			} 
		}
		
		return "";
	}
}
