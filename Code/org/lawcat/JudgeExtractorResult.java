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
