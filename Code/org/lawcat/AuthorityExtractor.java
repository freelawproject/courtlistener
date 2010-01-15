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
import java.util.regex.*;

public class AuthorityExtractor {
	
	//extract all United States Code cited
	static public Vector<String> uscExtractor(String text){
		
		Vector<String> uscVec = new Vector<String>();
		/*
		 * various forms:
		 * 17 U.S.C. § 101
		 * 17 U. S. C. § 101
		 * 17 U.S.C. §§ some_number
		 * 17 U.S.C. Sec. 505.12
		 * 17 U.S.C. §101
		 */

		Pattern pat = Pattern.compile("(\\d)+\\sU.(\\s)?S.(\\s)?C.\\s(([§¤])+|Sec.)(\\s)+(\\d)+");  //¤ from noah's pdf conversion error

		Matcher m;
		m = pat.matcher(text);
		
		while (m.find()) {
			String uscStr =  m.group();
			
			// ¤ (error) -> § (correct)
			uscStr = uscStr.replace('¤', '§');
			
			uscVec.add(uscStr);
		}
		
		return uscVec;
	}
	
	//extract all precedents cited
	static public Vector<String> precExtractor(String text){
		
		Vector<String> precVec = new Vector<String>();
		
		precVec.add("");
		
		return precVec;
	}
}
