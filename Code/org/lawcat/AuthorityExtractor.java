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
