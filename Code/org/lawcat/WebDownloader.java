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
