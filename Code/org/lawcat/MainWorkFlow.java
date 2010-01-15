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

import java.io.File;
import java.io.IOException;
import java.util.Date;

import java.util.Iterator;
import java.util.Vector;

public class MainWorkFlow {

	/**
	 * @param args
	 */
	public static void main(String[] args) {

		//CircuitCourtScraper.run();  //convert pdf to txt

		//String text = ReadFileAsStr.read("Classification/copyright_training/Midway_v_Artic_547 F. Supp._999.txt");
		
		/* lower court extractor -- good!
		String lowerCourt = LowerCourtExtractor.extract(text);		
		System.out.println(lowerCourt);
		*/
		
		/*
		* judge extractor, works great
		 
		try {
			JudgeExtractorResult result =  JudgeExtractor.extract(text);
			
			result.print();

			
		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		*/
		
		/*
		//citation extractor 
		Vector<String> uscVec = AuthorityExtractor.uscExtractor(text);
		for (int i = 0; i<uscVec.size(); i++ ){
			System.out.println( uscVec.get(i) );
		}
		*/
		
		//training data
		//in all copyright training data, how many cited 17 u.s.c?
		//why some do not cite 17 u.s.c.?
		
		//read each case in Classification/copyright_training one by one
		File copyrightTrainingDir = new File("Classification/non_copyright_testing");//
		File[] txtFiles = copyrightTrainingDir.listFiles();
		
		Vector<File> contain17USC = new Vector<File>();
		Vector<String> uscStrVec = new Vector<String>();
		
		Vector<File> no17USC = new Vector<File>();
		
		for (int i = 0; i<txtFiles.length; i++ ){ //for each file in training data
			try {
				
				String filePath = txtFiles[i].getCanonicalPath();
				
				String fileContent = ReadFileAsStr.read( filePath );
				
				Vector<String> uscVec = AuthorityExtractor.uscExtractor(fileContent);
				
				boolean has17USC = false;
				
				String uscStr = "";
				for (int j = 0; j<uscVec.size(); j++ ){ //each statute cited, contain 17 usc?
					uscStr = uscVec.get(j);
					if( uscStr.startsWith("17 U.") ){
						has17USC = true;
						break;
					}
				}
				
				if( has17USC ){
					contain17USC.add(txtFiles[i]);
					uscStrVec.add(uscStr);
				}
				else
					no17USC.add(txtFiles[i]);
				
			} catch (IOException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}
		}
			
		//files that contain 17 usc
		System.out.println("yes 17 usc: " + contain17USC.size() );
		for ( int i=0; i<contain17USC.size(); i++ ){
			System.out.println(contain17USC.get(i).getName() + '\t' + uscStrVec.get(i));
		}
		
		//files that does not contain 17 usc
		System.out.println();
		System.out.println("no 17 usc: " + no17USC.size());
		for ( int i=0; i<no17USC.size(); i++ ){
			System.out.println(no17USC.get(i).getName());
		}
	}

}
