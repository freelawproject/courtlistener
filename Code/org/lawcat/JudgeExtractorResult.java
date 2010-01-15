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

import java.util.Vector;

public class JudgeExtractorResult {
	
	Vector<String> names = new Vector<String>();
	Vector<String> titles = new Vector<String>();  

	private static String GetLastName(String name) {
		//System.out.println(name);
		// Get rid of jr. and sr.
		name = name.trim().replaceAll("\\s+[JS][Rr]\\.?$", "");
		//System.out.println(name.replaceAll(".*\\s+", ""));
		return name.replaceAll(".*\\s+", "");
	}
	
	private static String GetFirstInitial(String name) {
		return name.substring(0, 1);
	}
	
	public void print(){
		for (int i = 0; i < titles.size(); ++i) {
			
			String title = titles.get(i);
			String name = names.get(i);
			String first_initial = GetFirstInitial(name);
			String last_name = GetLastName(name).toUpperCase();
			
			System.out.println("title="+title+"\tfirst_initial="+first_initial+"\tlast_name="+last_name);
		}
	}
}
