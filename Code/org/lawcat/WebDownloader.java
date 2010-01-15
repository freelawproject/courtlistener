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

import java.io.BufferedOutputStream;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLConnection;
import java.util.Date;

public class WebDownloader {
	
	/**
	 * example: WebDownloader.SaveOpinion("http://www.google.com", "1cir/test.txt");
	 * @param address
	 * @param localFileName
	 */
	public static void Save(String address, String localFileName) {
		
		//record mapping of URL to local file name
		// downloadURL.txt: address+'\t'+ localFileName
		File downloadURL= new File("downloadURL.txt");
		if( ! downloadURL.exists() ){
			try {
				downloadURL.createNewFile();
			} catch (IOException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}
		}
		boolean append = true; 
		FileWriter fstream;
		try {
			fstream = new FileWriter(downloadURL, append);
			
			BufferedWriter bw_out = new BufferedWriter(fstream);
			Date today = new Date();
			bw_out.write(today.toString() + "\t" + address + "\t" + localFileName);
			bw_out.close();
			
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}

		
		//***********2nd part below
		
		
		//save web file to local disk
		File f = new File(localFileName);
		if (f.exists())
			return;  // Don't re-download files we already have
		System.out.print("Downloading " + address + "\n to " + localFileName + "...");
		OutputStream out = null;
		URLConnection conn = null;
		InputStream  in = null;
		try {
			URL url = new URL(address);
			out = new BufferedOutputStream(
				new FileOutputStream(localFileName));
			conn = url.openConnection();
			in = conn.getInputStream();
			byte[] buffer = new byte[1024];
			int numRead;
			long numWritten = 0;
			while ((numRead = in.read(buffer)) != -1) {
				out.write(buffer, 0, numRead);
				numWritten += numRead;
			}
			System.out.println("done");
		} catch (Exception exception) {
			exception.printStackTrace();
		} finally {
			try {
				if (in != null) {
					in.close();
				}
				if (out != null) {
					out.close();
				}
			} catch (IOException ioe) {
			}
		}
	}
}
