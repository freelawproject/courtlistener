package com.robocourt.extractors.citations;

import java.util.HashSet;
import java.util.Vector;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

import com.robocourt.util.ResourceHolder;


public class USSG extends Rule {
	
	private static final Pattern validation_pattern = Pattern.compile("^(\\d)([A-Z])(\\d+)\\.(\\d+)$");

	public USSG(ResourceHolder C) {
		super(C, "USSG");
		this.starters = new HashSet<Character>();
		this.starters.add('U');
		this.starters.add('u');
	}
	
	public USSG(int[] prev, int cid) {
		super(prev,
				new String[] {"ussg", "u.s.s.g."},
				"U.S.S.G. &sect;",
				cid);
	}
	
	public USSG newInstance(int[] prev) {
		return new USSG(prev, this.citation_type_id);
	}
	
	public String citation_url(int index) {
		String result =  "http://www.ussc.gov/2007guid/";
		result += this.rules[index].replace('.', '_').toLowerCase() + ".html";
		return result;
	}
	
	protected boolean ValidateSection(String section) {
		boolean result = validation_pattern.matcher(section).matches();
		//if (!result)
		//	System.out.println("USSG Rejected " + section);
		return result;
	}
	
	protected void Add(String section, String[] subsections,
			Vector<String> other_sections, Vector<String[]> other_subsections) {
		for (int i = 0; i < other_sections.size(); ++i) {
			if (section.equals(other_sections.get(i))) {
				// Found a match, so we need to combine
				//System.out.println("Found match between " + section + " and " + other_sections.get(i));
				int subsections_match = 0;
				String[] matching_subsection = other_subsections.get(i);
				int max_length = Math.min(subsections.length, matching_subsection.length);
				//System.out.println(" max_length = " + max_length);
				while (subsections_match < max_length &&
						subsections[subsections_match].equals(matching_subsection[subsections_match])) {
					++subsections_match;
				}
				// Find common subsections up to first one not in common
				String[] new_subsections = new String[subsections_match];
				for (int j = 0; j < subsections_match; ++j) {
					new_subsections[j] = subsections[j];
				}
				other_subsections.set(i, new_subsections);
				return;
			}
		}
		// No match found, so safe to add it
		other_sections.add(section);
		other_subsections.add(subsections);
	}
	
	public String sort_order(int index) {
		String result = "";
		
		Matcher m = validation_pattern.matcher(this.rules[index]);
		m.find();
		result += m.group(1);
		result += String.format("%02d", Character.digit(m.group(2).charAt(0), Character.MAX_RADIX));
		result += String.format("%02d", Integer.parseInt(m.group(3)));
		result += String.format("%02d", Integer.parseInt(m.group(4)));
		
		return result;
	}

}
