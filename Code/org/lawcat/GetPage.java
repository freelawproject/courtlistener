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
