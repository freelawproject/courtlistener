package org.lawcat;

import java.sql.ResultSet;
import java.sql.Statement;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.Arrays;


/*
 * Tries to figure out which lower court's decision is being reviewed
 */

public class LowerCourtExtractor {
	
	// words ending state names; keep in alphabetical order
	private static final String[] STATE_WORDS = 
		{ "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA", "CAROLINA", "CAROLINA", "COLORADO", "COLUMBIA", "CONNECTICUT",
			"DAKOTA", "DAKOTA", "DELAWARE", "FLORIDA", "GEORGIA", "HAMPSHIRE", "HAWAII", "HAWAI'I", "IDAHO", "ILLINOIS", "INDIANA",
			"IOWA", "ISLAND", "ISLANDS", "JERSEY", "KANSAS", "KENTUCKY", "LOUISIANA", "MAINE", "MARYLAND", "MASSACHUSETTS",
			"MEXICO", "MICHIGAN", "MINNESOTA", "MISSISSIPPI", "MISSOURI", "MONTANA", "NEBRASKA", "NEVADA",
			"OHIO", "OKLAHOMA", "OREGON", "PA", "PENNSYLVANIA", "RICO", "TENNESSEE", "TEXAS", "UTAH", "VERMONT", "VIRGINIA",
			"VIRGINIA", "WASHINGTON", "WISCONSIN", "WYOMING", "YORK" };

	// keep this in alphabetical order
	private static final String[] UNIMPORTANT = 
		{ "COURT", "DISTRICT", "FOR", "OF", "STATE", "STATES", "THE", "UNITED" };
	
	// keep in alphabetical order
	private static final String[] COLORADO_ABBREVS = 
		{ "D.Colo.", "D.Colorado", "D.Kan.", "D.Kans.", "D.Kansas", "D.N.M.", 
		 "D.NewMexico", "D.Utah",  "D.Wyo.", "D.Wyom.", "D.Wyoming",  "E.D.Okla.",
		"E.D.Oklahoma", "N.D.Okla.", "N.D.Oklahoma", "W.D.Okla.", "W.D.Oklahoma" };
	
	private static final String[] COLORADO_EXPANDED = 
	{ "District of Colorado", "District of Colorado", "District of Kansas", "District of Kansas", "District of Kansas", "District of New Mexico"
		, "District of New Mexico"	, "District of Utah",
	"District of Wyoming", "District of Wyoming", "District of Wyoming", 
	"Eastern District of Oklahoma", "Eastern District of Oklahoma", "Northern District of Oklahoma",
	"Northern District of Oklahoma", "Western District of Oklahoma", "Western District of Oklahoma" };

	// keep this in alphabetical order
	private static final String[] UNCAPITALIZED = 
		{ "FOR", "OF", "THE" };
	
	// capitalize a single word
	private static String Capitalize(String word) {
		if (Arrays.binarySearch(UNCAPITALIZED, word.toUpperCase()) < 0) {
			// capitalize it
			return word.substring(0,1).toUpperCase() + word.substring(1).toLowerCase();
		}
		return word.toLowerCase();
	}
	
	private static String StripCrap(String word) {
		return word.replaceAll("[^A-Za-z]+", "");
	}
	
	private static String FindWords(String text) {
		String result = "";
		String word;
		Pattern word_pattern = Pattern.compile("(\\w+)[\\.,;]?\\s*");
		Matcher matcher = word_pattern.matcher(text);
		boolean found = false;
		int i = 0;
		// Look at next 25 words; stop when there's a newline
		// and you have found an important word
		while(i++ < 25 & matcher.find()) {
			word = StripCrap(matcher.group(1));
			if (word.length() < 2) continue;  // probably junk
			result += Capitalize(word.trim()) + " ";
			// System.out.println(result);
			//if (Arrays.binarySearch(UNIMPORTANT, word.trim().toUpperCase()) < 0) {
			//	found = true;
			//}
			if (Arrays.binarySearch(STATE_WORDS, word.trim().toUpperCase()) >= 0) {
				found = true;
				break;
			}
		}
		if (found)
			return result.substring(0, result.length()-1);
		return "";
	}

	public static String extract(String text) {
		Matcher matcher;
		String beginning = text.substring(0, Math.min(10000, text.length()));
		
		// First look for district court appellate information
		// System.out.println(beginning);
		Pattern appeal_pattern = Pattern.compile(
				"APPEALS?.{0,1000}?UNITED[^A-Za-z]+STATES[^A-Za-z]+DISTRICT[^A-Za-z]+COURT[^A-Za-z]+(?:FOR|OF)[^A-Za-z]+THE[^A-Za-z]+",
				Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
		matcher = appeal_pattern.matcher(beginning);
		if (matcher.find()) {
			String result = FindWords(text.substring(matcher.end()));
			if (!result.equals("")) return "Appeal from the " + result;
		}
		
		
		// Now try BIA
		// System.out.println(beginning);
		Pattern BIA_pattern = Pattern.compile(
				"REVIEW?.{0,100}(?:(?:BOARD[^A-Za-z]+OF[^A-Za-z]+IMMIGRATION[^A-Za-z]+APPEALS)|\\bBIA\\b)",
				Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
		matcher = BIA_pattern.matcher(beginning);
		if (matcher.find()) {
			return "Review of Board of Immigration Appeals decision";
		}

		// Try another regex that uses less of the text but doesn't need the word "appeal"
		appeal_pattern = Pattern.compile(
				"(?:(?:CENTRAL|MIDDLE|EASTERN|WESTERN|NORTHERN|SOUTHERN)[^A-Za-z]+)?DISTRICT[^A-Za-z]+OF",
				Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
		matcher = appeal_pattern.matcher(beginning.substring(0, Math.min(500, beginning.length())));
		if (matcher.find()) {
			String result = FindWords(text.substring(matcher.start()));
			result = result.replaceAll("^[Tt][Hh][Ee]\\s+", "");
			result = result.replaceAll("^[A-Za-z]{1,2}\\s+", "");
			if (!result.equals("")) return "Appeal from the " + result;
		}

		// Just for Colorado--gah
		appeal_pattern = Pattern.compile(
				"\\((([WEN]\\.\\s*)?D\\.[^\\)]+)\\)",
				Pattern.CASE_INSENSITIVE);
		//System.out.println(beginning.substring(0, Math.min(1000, beginning.length())));
		matcher = appeal_pattern.matcher(beginning.substring(0, Math.min(2000, beginning.length())));
		String result = "";
		while (result == "" && matcher.find()) {
			result = matcher.group(1);
			//System.out.println(result);
			result = result.replaceAll("\\s+of", "");
			result = result.replaceAll("\\s+", "");
			int index = Arrays.binarySearch(COLORADO_ABBREVS, result);
			if (index >= 0) {
				result = COLORADO_EXPANDED[index];
			}
			else {
				result = "";
				//System.out.println("Couldn't find something for " + result);
			}
			//String result = FindWords(text.substring(matcher.start()));
			//result = result.replaceAll("^[Tt][Hh][Ee]\\s+", "");
			//result = result.replaceAll("^[A-Za-z]{1,2}\\s+", "");
			if (!result.equals("")) return "Appeal from the " + result;
		}
		
		// Oh well
		return "";
	}
	
	
}
