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
