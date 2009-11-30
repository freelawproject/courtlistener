package com.robocourt.extractors.citations;

import com.robocourt.util.ResourceHolder;

// For now, treats it as a citation into plain US Code
public class USCodeAnnotated extends USCode {
	
	public USCodeAnnotated(int[] prev, int cid) {
		super(prev, cid);
		this.matching_strings =
			new String[] {"u.s.c.s.", "u.s.c.a.",
				"usca", "uscs",
				"u. s. c. a.", "u. s. c. s."};
	}
	
	public USCodeAnnotated(ResourceHolder C) {
		super(C);
	}
	
	public USCode newInstance(int[] prev) {
		return new USCodeAnnotated(prev, this.citation_type_id);
	}

}
