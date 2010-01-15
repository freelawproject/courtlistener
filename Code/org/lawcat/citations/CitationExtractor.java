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


package org.lawcat.citations;


import java.util.Vector;
import java.util.HashMap;

import com.robocourt.extractors.citations.CitationType;
import com.robocourt.util.Connect;
import com.robocourt.util.ResourceHolder;

/*
 * Citation extraction workhorse. Give it an array of citation types and it will advance
 * through the text, trying to parse each citation type in parallel.
 */

public class CitationExtractor {
	
	// status codes for citation types:
	public static final int PARSE_BROKEN = 0;
	public static final int PARSE_IN_PROGRESS = 1;
	public static final int MORE_INFO_NEEDED = 3;
	public static final int PARSE_COMPLETE = 4;
	// information types:
	public static final int STATUTE_TYPE = 0;
	public static final int OPINION_TYPE = 1;
	public static final int PATENT_TYPE = 2;
	
	private static final int NUM_PARSED_NUMBERS = 3;  // number of parsed numbers to remember
	
	private CitationType[] citation_type_creators; // used to create new citation parsers
	private Vector<CitationType> citation_types;   // currently in use
	private CitationType waiting;
	private int waiting_type;
	
	private String text;  // text to parse
	private int pos;  // current position in the text
	
	// Helpers for parsing
	private int[] numbers;  // last few numbers parsed
	private Vector<HashMap<String, String>> info;  // information to pass to citation types
	
	Vector<CitationType> parsed;  // citations already parsed
	
	public CitationExtractor(CitationType[] ctc) {
		this.citation_type_creators = ctc;
		init();
	}
	
	private void init() {
		this.citation_types = new Vector<CitationType>();
		this.pos = 0;
		this.numbers = new int[NUM_PARSED_NUMBERS];
		this.waiting = null;
		this.waiting_type = -1;
		this.info = null;
		this.parsed = new Vector<CitationType>();
	}
	
	// advance all parsers and attempt to create new ones of each type
	private void StepParsers(int skipped) {
		pos -= skipped;
		int num_steps = skipped;
		if (skipped == 0)
			num_steps = 1;
		for (int step = 0; step < num_steps; ++step) {
			// Add new parsers of each type starting at current character
			char c = text.charAt(pos);
			for (int i = 0; i < citation_type_creators.length; ++i) {
				if (citation_type_creators[i].start(c))
					citation_types.add(citation_type_creators[i].newInstance(numbers));
			}
			for (int j = 0; j < citation_types.size();) {
				CitationType t = citation_types.get(j);
				if (t.input(c) == PARSE_BROKEN) {
					citation_types.remove(j);
				}
				else if (t.status() == MORE_INFO_NEEDED) {
					// This one may be done after we send it page numbers, etc.
					this.waiting = t;
					this.waiting_type = t.info_type();
					//System.out.println("more info needed: " + this.waiting_type);
					citation_types.remove(j);
				}
				else {
					++j;
				}
			}
			++this.pos;
		}
		if (skipped == 0)
			this.numbers = new int[NUM_PARSED_NUMBERS];
	}
	
	// if we are at the beginning of a number, add it to the numbers array
	// returns the number of characters involved (NOT the number parsed)
	private int ParseInt(boolean allow_commas) {
		String str = "";
		while (this.pos < this.text.length() 
				&& Character.isDigit(this.text.charAt(this.pos))) {
			str += this.text.charAt(this.pos++);
			if(allow_commas && this.pos < this.text.length() - 1
					&& this.text.charAt(this.pos) == ','
						&& Character.isLetterOrDigit(this.text.charAt(this.pos + 1))) {
				// Comma in the middle of a number
				str += "," + this.text.charAt(this.pos + 1);
				this.pos += 2;
			}
		}
		if (str.length() > 0) {
			if (this.pos < this.text.length() - 2 &&
					(Character.isLetter(this.text.charAt(this.pos))
					|| ( this.text.charAt(this.pos) == '.'
						&& Character.isDigit(text.charAt(this.pos + 1))))) {
				this.pos -= str.length();
				return 0;
			}
			else {
				// shift numbers array
				for (int i = 0; i < NUM_PARSED_NUMBERS - 1; ++i) {
					numbers[i+1] = numbers[i];
				}
				// add new number
				int num = -1;
				try {
					num = Integer.parseInt(str.replaceAll(",", ""));
				}
				catch (Exception e) {
					// If we failed to parse then give up
					this.pos -= str.length();
					return 0;
				}
				//System.out.println("Adding " + num);
				numbers[0] = num;
			}
		}
		return str.length();
	}
	
	// include non-breaking spaces
	private boolean IsWhitespace(int cp) {
		return (Character.isWhitespace(cp)
			|| (cp == '\u00A0')
			|| (cp == '\u2007')
			|| (cp == '\u202F'));
	}
	
	// returns number of characters skipped
	private int SkipWhiteSpace() {
		int result = 0;
		while(this.pos < this.text.length() 
				&& IsWhitespace(this.text.codePointAt(this.pos))) {
			this.pos++;
			result++;
		}
		return result;
	}
	
	private int GetSubsections(int info_index) {
		//System.out.println("1:" + this.text.charAt(this.pos));
		int start = this.pos;
		int last_match = start;
		boolean found_subsection;
		String str = "section";
		do {
			found_subsection = false;
			SkipWhiteSpace();
			if (this.pos < this.text.length() && this.text.charAt(this.pos++) == '(') {
				String subsection = "";
				while (this.pos < this.text.length() && Character.isLetterOrDigit(this.text.charAt(pos))) {
					subsection += this.text.charAt(this.pos++);
					if (subsection.length() > 2) {
						// must have found other parenthetical remark
						this.pos = last_match;
						break;
					}
				}
				if (this.pos < this.text.length() && this.text.charAt(this.pos++) == ')') {
					found_subsection = true;
					str = "sub" + str;
					info.get(info_index).put(str, subsection);
					last_match = this.pos;
				}
				else {
					this.pos = last_match;
				}
			}
			else {
				this.pos--;
			}
		} while (found_subsection == true);
		//System.out.println("2:" + this.text.charAt(this.pos));
		return this.pos - start;
	}
	
	// Default: no commas allowed
	private int ParseSection(int info_index) {
		return ParseSection(info_index, false);
	}
	
	// Gets section information, including subsection
	private int ParseSection(int info_index, boolean allow_commas_in_numbers) {
		// Try to parse a number; if that fails parse more general section
		int skip = ParseInt(allow_commas_in_numbers);
		String section = "";
		if (skip == 0) {
			while (this.pos < this.text.length()
					&& (Character.isLetterOrDigit(this.text.charAt(this.pos))
						|| this.text.charAt(this.pos) == '.')) {
				section += this.text.charAt(this.pos);
				this.pos++;
				skip++;
			}
		}
		else {
			section = String.format("%d", numbers[0]);
		}
		if (skip > 0) {
			//System.out.println("just parsed " + numbers[0] + " in " + skip + " digits");
			this.info.get(info_index).put("section", section);
		}
		return skip + GetSubsections(info_index);
	}
	
	private int ParsePageNumber(String type, int info_index) {
		int skip = ParseInt(false);  // no commas
		if (skip > 0) {
			String str = String.format("%d", numbers[0]);
			if (numbers[1] > -1) {
				// look out for things like 1224-25
				String str2 = String.format("%d", numbers[1]);
				String str1 = str;
				String extra = "";
				for (int i = 0; i < str2.length() - str1.length(); ++i) {
					extra += str2.charAt(i);
				}
				str = extra + str;
			}
			info.get(info_index).put(type, str);
		}
		return skip;
	}
	
	private void Finish(CitationType t) {
		// Try to merge it with an existing citation
		for (int i = 0; i < this.parsed.size(); ++i) {
			if (this.parsed.get(i).merge(t))
				return;
		}
		// Otherwise add it as a new citation
		this.parsed.add(t);
	}
	
	
	// Add section information if a statute is waiting 
	// TODO: implement MORE_INFO_NEEDED
	private void SendInfo() {
		if (this.waiting == null)
			return;
		//System.out.println("applying section info");
		this.waiting.AddInformation(info.toArray(new HashMap[]{}));
		if (this.waiting.status() == PARSE_COMPLETE) {
			Finish(this.waiting);
		}
		this.waiting = null;
	}
	
	// TODO: implement MORE_INFO_NEEDED
	private void SendAtInfo() {
		if (this.waiting == null || this.parsed.size() == 0)
			return;
		int best_match_distance = CitationType.INFINITY;
		int best_index = 0;
		for (int i = 1; i < this.parsed.size(); ++i) {
			int distance = this.parsed.get(i).Distance(this.waiting, this.info.toArray(new HashMap[]{}));
			if (distance < best_match_distance) {
				best_match_distance = distance;
				best_index = i;
			}
		}
		this.parsed.get(best_index).AddInformation(info.toArray(new HashMap[]{}));
		if (this.waiting.status() == PARSE_COMPLETE) {
			Finish(this.waiting);
		}
		this.waiting = null;
	}
	
	// Skip "¤"
	private int SkipSectionDelimiter() {
		int skip = 0;
		if (this.pos < this.text.length()
				&& this.text.charAt(this.pos) == '¤') {
			this.pos++;
			skip++;
		}
		return skip;
	}
	
	// Skip "and"
	private int SkipAnd() {
		int skip = 0;
		if (this.pos < this.text.length() - 3
				&& this.text.substring(this.pos, this.pos + 3).equals("and")
				&& Character.isWhitespace(this.text.charAt(this.pos + 3))) {
			this.pos += 3;
			skip += 3;
			skip += SkipWhiteSpace();
		}
		return skip;
	}
	
	// Skip the parenthetic remark if we are at one
	private int SkipParenthetic() {
		int skip = 0;
		int depth = 0;
		if (this.pos < this.text.length()
				&& this.text.charAt(this.pos) == '(') {
			depth = 1;
			this.pos++;
			skip++;
			while (this.pos < this.text.length() && depth > 0) {
				if (this.text.charAt(this.pos) == '(')
					depth += 1;
				else if (this.text.charAt(this.pos) == ')')
					depth -= 1;
				skip++;
				this.pos++;
			}
		}
		return skip;
	}
	
	// parses numbers and special words
	private int ParseSpecial() {
		int skip = SkipWhiteSpace();
		this.info = new Vector<HashMap<String, String>>();
		
		if (this.waiting_type == STATUTE_TYPE) {
			// System.out.println("looking for info");
			// Look for statute-type citation information
			
			skip += this.SkipSectionDelimiter();
			boolean multiple = false;
			int n = this.SkipSectionDelimiter();
			if (n > 0)
				multiple = true;
			skip += n;
			this.info.add(new HashMap<String, String>());
			skip += SkipWhiteSpace();
			skip += ParseSection(0);
			// if multiple then look for more citations until break
			int info_index = 1;
			while (multiple) {
				//System.out.println("looking for more");
				//System.out.println(this.text.substring(this.pos, this.pos + 3));
				skip += SkipWhiteSpace();
				int s = 0;
				if (this.pos < this.text.length()
						&& this.text.charAt(this.pos) == ',') {
					// add another one
					this.info.add(new HashMap<String, String>());
					this.pos++;
					skip++;
					skip += SkipWhiteSpace();
					// Get rid of another "and" if it is there
					skip += SkipAnd();
					skip += ParseSection(info_index++);
				}
				else if ((s = SkipAnd() ) > 0) {
					// add another one; last one
					this.info.add(new HashMap<String, String>());
					skip += s;
					skip += ParseSection(info_index++);
					break;
				}
				else {
					// can't find another one
					break;
				}
			}
			SendInfo(); // for you: higher level ; use example ; open adr; schedule: 8:30 in my time
		}
		else if (this.waiting_type == OPINION_TYPE) {
			//System.out.println("looking for opinion info");
			this.info.add(new HashMap<String, String>());
			
			// Get entry/citation page
			skip += SkipWhiteSpace();
			
			if (this.pos < this.text.length() - 2
					&& this.text.substring(this.pos, this.pos + 2).equals("at")
					&& Character.isWhitespace(this.text.charAt(this.pos + 2))) {
				// handle "at" reference
				//System.out.println(this.text.substring(this.pos, this.pos + 10));
				this.pos += 3;
				skip += 3 + SkipWhiteSpace();
				skip += ParsePageNumber("start", 0);
				if (this.pos < this.text.length()
						&& this.text.charAt(this.pos) == '-') {
					this.pos++;
					skip++;
					skip += SkipWhiteSpace();
					skip += ParsePageNumber("end", 0);
				}
				SendAtInfo();
			}
			else {
				skip += ParsePageNumber("entry", 0);
				
				// Get further pages
				skip += SkipWhiteSpace();
				if (this.pos < this.text.length()
						&& this.text.charAt(this.pos) == ',') {
					this.pos++;
					skip++;
					skip += SkipWhiteSpace();
					skip += ParsePageNumber("start", 0);
					if (this.pos < this.text.length()
							&& this.text.charAt(this.pos) == '-') {
						this.pos++;
						skip++;
						skip += SkipWhiteSpace();
						skip += ParsePageNumber("end", 0);
					}
				}
				SendInfo();
			}
		}
		else if (this.waiting_type == PATENT_TYPE) {
			boolean multiple = false;
			if (this.pos < this.text.length()
					&& Character.toLowerCase(this.text.charAt(this.pos)) == 's') {
				multiple = true;
				++skip;
				this.pos++;
			}
			
			skip += SkipWhiteSpace();
			if (this.pos < this.text.length()
					&& this.text.charAt(this.pos) == '.') {
				skip++;
				this.pos++;
				skip += SkipWhiteSpace();
			}
			this.info.add(new HashMap<String, String>());
			int s = ParseSection(0, true);  // parse section with commas
			skip += s;
			if (s > 0 && multiple) {
				this.info.add(new HashMap<String, String>());
				skip += SkipWhiteSpace();
				skip += SkipParenthetic();
				skip += SkipWhiteSpace();
				// Skip comma
				if (this.pos < this.text.length()
						&& this.text.charAt(this.pos) == ',') {
					this.pos++;
					skip++;
					skip += SkipWhiteSpace();
				}
				skip += SkipAnd();
				skip += ParseSection(1, true);
			}
			if (s > 0)
				SendInfo();
		}
		
		if (skip == 0) {
			// Try getting a number
			skip += ParseInt(false);
		}
		
		// TODO: deal with needing more than one piece of information
		this.waiting = null;
		this.waiting_type = -1;
		
		return skip;
	}
	
	// return the i-th most recently parsed number (index starts at 0)
	public int GetParsedInt(int i) {
		if (i > NUM_PARSED_NUMBERS)
			return -1;
		return numbers[i-1];
	}
	
	// Parse text
	public void go(String str, boolean print_found) {
		init();
		this.text = str;
		while (this.pos < this.text.length()) {
			int skip = ParseSpecial();
			StepParsers(skip);
		}
		if (print_found) {
			for (int j = 0; j < parsed.size(); ++j) {
				CitationType t = parsed.get(j);
				for (int i = 0; i < t.num_citations(); ++i) {
					System.out.println("Finished:\n " + t.citation_string(i));
					System.out.println(" " + t.citation_url(i));
				}
			}
		}
	}
	
	public void go(String str) {
		go(str, false);
	}
	
	public CitationType[] result() {
		return parsed.toArray(new CitationType[] {});
	}

	/*
	 * Extract all citations from all opinions in the database.
	 * If diff_only is true then just note the difference from the citations already
	 * in the database; otherwise update the database.
	 */
	private void FindAllCitations(boolean diff_only) throws Exception {
		Connect C = new Connect();
		Statement s = C.connection().createStatement();
		if (!diff_only)
			s.executeUpdate("TRUNCATE TABLE citations");
		int count = 0;
		int quantity = 200;  // how many to get at a time
		int iterations = 0;
		// Go 100 at a time to avoid running out of memory
		do {
			count = 0;
			s = C.connection().createStatement();
			String query = "SELECT id,text,title,date FROM opinions LIMIT " + quantity + " OFFSET " + (iterations++ * quantity);
			System.out.println(query);
			s.executeQuery(query);
			ResultSet rs = s.getResultSet();
			while (rs.next()) {
				if (diff_only) {
					System.out.println(rs.getString("title") + " (" + rs.getString("id") + ") (" + rs.getString("date") + ")");
				}
				//System.out.println(rs.getString("id"));
				this.go(rs.getString("text"));
				CitationType[] result = this.result();
				String exclude_clause = "1";
				for (int i = 0; i < result.length; ++i) {
					CitationType t = result[i];
					for (int j = 0; j < t.num_citations(); ++j) {
						String url = t.citation_url(j);
						String txt = t.citation_string(j);

						if (diff_only) {
							// Note new citations
							exclude_clause += " AND text != '" + Connect.mysql_escape(txt) + "'";
							s = C.connection().createStatement();
							query = "SELECT * FROM citations WHERE opinion_id = " + rs.getString("id") + " AND text = '" + Connect.mysql_escape(txt) + "'";
							s.executeQuery(query);
							ResultSet rs2 = s.getResultSet();
							if (!rs2.next()) {
								System.out.println("  New: " + txt);
							}
						}
						else {
							s = C.connection().createStatement();
							query = "INSERT INTO citations (opinion_id, type_id, text, url, sort_order) VALUES ("
								+ rs.getString("id") + ", "
								+ t.citation_type_id() + ", '"
								+ Connect.mysql_escape(txt) + "', '"
								+ Connect.mysql_escape(url) + "', "
								+ t.sort_order(j) + ")";
							//System.out.println(query);
							s.executeUpdate(query);
						}
					}
				}
				if (diff_only) {
					// Note missing citations
					s = C.connection().createStatement();
					query = "SELECT text FROM citations WHERE (" + exclude_clause + ") AND opinion_id = " + rs.getString("id");s.executeQuery(query);
					ResultSet rs2 = s.getResultSet();
					while (rs2.next()) {
						String txt = rs2.getString("text");
						System.out.println("  Missing: " + txt);
					}
				}
				++count;
				//L.add(new Opinion(rs.getString("title"), rs.getInt("court_id"), rs.getString("url"), rs.getDate("date"), C, rs.getString("url").contains("pdf")));
			}
			rs.close();
		} while (count != 0);
		System.out.println("Finished!");
	}
	
	private void TestOne(int id, ResourceHolder  C) throws Exception{
		
		Statement s = C.connection().createStatement();
		String query = "SELECT text FROM opinions WHERE id = " + id;
		s.executeQuery(query);
		ResultSet rs = s.getResultSet();
		rs.next();
		this.go(rs.getString("text"), true);
	}
	
	public static void main(String[] args) throws Exception {
		ResourceHolder C = new ResourceHolder();
		CitationType[] types = new CitationType[] {
				new com.robocourt.extractors.citations.CFR(C),
				new com.robocourt.extractors.citations.USCode(C),
				new com.robocourt.extractors.citations.USCodeAnnotated(C),
				new com.robocourt.extractors.citations.F1(C),
				new com.robocourt.extractors.citations.F2(C),
				new com.robocourt.extractors.citations.F3(C),
				new com.robocourt.extractors.citations.FSupp1(C),
				new com.robocourt.extractors.citations.FSupp2(C),
				new com.robocourt.extractors.citations.FedRAppP(C),
				new com.robocourt.extractors.citations.FedRCivP(C),
				new com.robocourt.extractors.citations.FedRCrimP(C),
				new com.robocourt.extractors.citations.FedREvid(C),
				new com.robocourt.extractors.citations.USPatent(C),
				new com.robocourt.extractors.citations.USTM(C),
				new com.robocourt.extractors.citations.USSG(C),
				new com.robocourt.extractors.citations.SCOTUS(C)
				};
		CitationExtractor E = new CitationExtractor(types);
		//E.TestOne(3, C);
		//E.TestOne(1712, C);
		//E.TestOne(1929, C);
		//E.FindAllCitations(true);  // Test for differences
		E.FindAllCitations(false);  // Recreate citations table
	}
	
}
