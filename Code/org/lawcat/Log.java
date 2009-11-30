package org.lawcat;

import java.io.*;
import java.util.Date;

public class Log {
	
	static File logFile= new File("log.txt");
	
	static public void createLog(){

		//create log file
		if( ! logFile.exists() ){
			try {
				logFile.createNewFile();
			} catch (IOException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}

		}
		
	}
	
	static public void writeLog(String s){
		try {
			boolean append = true; 
			FileWriter fstream = new FileWriter(logFile, append);
			BufferedWriter out = new BufferedWriter(fstream);
			Date today = new Date();
			out.write(today.toString() + ":\t" + s);
			out.close();
						
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
	}
	
	static public void printLog(){
		
	}
	
}
