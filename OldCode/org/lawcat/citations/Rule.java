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


package com.robocourt.extractors.citations;

/*
 * Base class for citations to rules or laws
 */


import java.util.HashMap;
import java.util.Vector;

import com.robocourt.extractors.CitationExtractor;
import com.robocourt.util.ResourceHolder;

public class Rule extends SubstringMatcher implements CitationType {
	
	protected String[] rules = null;
	protected String[][] subsections = new String[0][0];
	protected String display_name;
	protected int citation_type_id;
	
	public Rule(ResourceHolder C, String db_name) {
		this.matching_strings = new String[0];
		this.citation_type_id = C.getCitationTypeID(db_name);
		init();
	}
	
	public Rule(int[] prev, String[] matching, String dn, int cid) {
		this.display_name = dn;
		this.matching_strings = matching;
		this.citation_type_id = cid;
		init();
	}
	
	private void init() {
		this.indexes = new int[this.matching_strings.length];
		this.finished = false;
		this.more_info = false;
		this.input = "";
	}
	
	// Override for custom validation
	protected boolean ValidateSection(String section) {
		try {
			Integer.parseInt(section);
			return true;
		}
		catch (Exception E) {
			// not a number, kill it
			return false;
		}
	}
	
	// Override to do things like combine upon add
	protected void Add(String section, String[] subsections,
			Vector<String> other_sections, Vector<String[]> other_subsections) {
		for (int i = 0; i < other_sections.size(); ++i) {
			if (section.equals(other_sections.get(i))) {
				// section match
				boolean match = false;
				if (subsections.length == other_subsections.get(i).length) {
					match = true;
					for (int j = 0; j < subsections.length; ++j) {
						if (!subsections[j].equals(other_subsections.get(i)[j]))
							match = false;
					}
				}
				if (match) {
					return;  // don't add exact match
				}
			}
		}
		other_sections.add(section);
		other_subsections.add(subsections);
	}
	
	
	protected void AddNewSection(String section, String[] subs) {
		Vector<String> rulesV = new Vector<String>();
		Vector<String[]> subsV = new Vector<String[]>();
		for (int i = 0; i < rules.length; ++i) {
			rulesV.add(rules[i]);
			subsV.add(this.subsections[i]);
		}
		this.Add(section, subs, rulesV, subsV);
		this.rules = rulesV.toArray(new String[]{});
		this.subsections = subsV.toArray(new String[][]{});
	}

	public void AddInformation(HashMap<String, String>[] info) {
		if (info == null || info.length == 0 || !info[0].containsKey("section"))
			return;
		Vector<String> rulesV = new Vector<String>();
		Vector<String[]> subsV = new Vector<String[]>();
		for (int i = 0; i < info.length; ++i) {
			HashMap<String, String> piece = info[i];
			String section;
			if (piece.containsKey("section")) {
				//System.out.println("received section " + piece.get("section"));
				section = piece.get("section");
				if (!ValidateSection(section))
					break;
			}
			else if (rulesV.size() > 0) {
				section = rulesV.get(rulesV.size() - 1);
			}
			else {
				// can't figure out what section is
				break;
			}
			String str = "subsection";
			Vector<String> subsectionsV = new Vector<String>();
			while (piece.containsKey(str)) {
				subsectionsV.add(piece.get(str));
				str = "sub" + str;
			}
			this.Add(section, subsectionsV.toArray(new String[] {}), rulesV, subsV);
		}
		this.rules = rulesV.toArray(new String[]{});
		this.subsections = subsV.toArray(new String[][]{});
		this.finished = true;
	}
	
	protected String JoinSubsectionPiecesForDisplay(int index) {
		String result = "";
		if (this.subsections[index] == null)
			return result;
		for (int i = 0; i < this.subsections[index].length; ++i)
			result += "(" + this.subsections[index][i] + ")";
		return result;
	}
	
	public int num_citations() {
		return this.rules.length;
	}

	public String citation_string(int index) {
		return this.display_name + this.rules[index] + JoinSubsectionPiecesForDisplay(index);
	}
	
	protected String JoinSubsectionPiecesForURL(int index) {
		String result = "";
		for (int i = 0 ; i < this.subsections[index].length; ++i) {
			result += this.subsections[index][i];
			if (i < this.subsections[index].length - 1) result += "_";
		}
		return result;
	}
	
	public String citation_url(int index) {
		return "";
	}

	public CitationType newInstance(int[] prev) {
		return null;
	}
	
	public int info_type() {
		return CitationExtractor.STATUTE_TYPE;
	}
	
	public int Distance(CitationType t, HashMap[] info) {
		return CitationType.INFINITY;
	}
	
	public int citation_type_id() {
		return this.citation_type_id;
	}
	
	public String sort_order(int index) {
		return String.format("%02d", Integer.parseInt(this.rules[index]));
	}
	
	public boolean merge(CitationType type) {
		if (type.getClass().equals(this.getClass())) {
			Rule t = (Rule)type;
			// Merge if there is any match in section
			boolean match_found = false;
			for (int i = 0; i < this.rules.length && !match_found; ++i) {
				for (int j = 0; j < t.rules.length && !match_found; ++j) {
					//System.out.println("Comparing " + this.getClass() + ": " + this.rules[i] + " vs. " + t.rules[j]);
					if (this.rules[i].equals(t.rules[j]))
						match_found = true;
				}
			}
			if (match_found) {
				//System.out.println("Merging " + this.getClass());
				for (int j = 0; j < t.rules.length; ++j) {
					this.AddNewSection(t.rules[j], t.subsections[j]);
				}
				return true;
			}
		}
		return false;
	}

}
