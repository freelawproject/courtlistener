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

import java.sql.ResultSet;
import java.sql.Statement;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.Vector;
import java.util.Arrays;
import java.util.HashMap;

public class JudgeExtractor {

	private static HashMap<String, Integer> cache;

	// Signals that we're at the end of a listing
	private static final String[] MAGIC_WORDS = new String[]
	 	{ "CHIEF", "CIRCUIT", "DISTRICT" };
	

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

	
	public static JudgeExtractorResult extract(String text) throws Exception {
		Pattern pattern = Pattern.compile(
				"B[Ee][Ff][Oo][Rr][Ee]");
		Matcher matcher = pattern.matcher(text);
		if (!matcher.find()) return new JudgeExtractorResult();
		int i = matcher.end();
		pattern = Pattern.compile("((?:[JS][rR]\\.)|(?:[A-Za-z'Õ]+(?:\\.[A-Za-z])?))[\\s\\.,;]");
		text = text.substring(i);
		matcher = pattern.matcher(text);
		String str = "";  // string we're building up as we parse
		Vector<String> names = new Vector<String>();
		Vector<String> titles = new Vector<String>();  // what type of judge are they?
		String current_title = null;
		boolean hit_magic_word = false;  // in the middle of a judge title
		boolean know_whether_before = false;  // title comes before name?
		boolean before = false;
		int words = 0;  // words since last judge name completed;
		int last_end = text.length();
		while(matcher.find() && words < 7) {  // bound names size to prevent running away
			int word_start = matcher.start();
			if (word_start > last_end + 6)
				break;  // too much, probably picking up crap
			int word_end = matcher.end(1);
			last_end = word_end;
			String word = matcher.group(1);
			
			//System.out.println(str + "/" + word + "/" + match);
				
			if (hit_magic_word &&
				word.matches("[Jj][Uu][Dd][Gg][Ee][Ss]?\\.?")) {
				if (!know_whether_before) {
					know_whether_before = true;
					if (names.isEmpty())
						before = true;
				}
				if (before) {
					current_title = str;
				}
				else {
					for (int j = titles.size(); j < names.size(); ++j) {
						//System.out.println(str);
						titles.add(str);
					}
				}
				str = "";
				words = 0;
				continue;
			}
			
			if (word.toUpperCase().equals("AND")) {
				if (!str.equals("")) {
					names.add(str);
					if(current_title != null)
						titles.add(current_title);
					str = "";
				}
				hit_magic_word = false;
				words = 0;
				continue;
			}
			
			if (Arrays.binarySearch(MAGIC_WORDS, word.toUpperCase()) >= 0) {
				hit_magic_word = true;
			}
			
			if (str.equals(""))
				str = word;
			else
				str += " " + word;
			++words;
			
			if (text.charAt(word_end) == ',') {
				// end of judge name
				// UNLESS it's a jr. or sr., dammit
				if (text.length() > word_end + 4
						&& (text.charAt(word_end + 2) == 'J'
							|| text.charAt(word_end + 2) == 'S')
						&& (text.charAt(word_end + 3) == 'r'
							|| text.charAt(word_end + 3) == 'R')
						&& text.charAt(word_end + 4) == '.')
					continue;
				//System.out.println("Found " + current_judge);
				names.add(str);
				if(current_title != null)
					titles.add(current_title);
				str = "";
				hit_magic_word = false;
				words = 0;
			}
		}

		JudgeExtractorResult result = new JudgeExtractorResult();
		result.titles = titles;
		result.names = names;
		
		return result;
	}

}
