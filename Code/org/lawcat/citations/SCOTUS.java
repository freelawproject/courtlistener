package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class SCOTUS extends Reporter implements CitationType {
	
	public SCOTUS(ResourceHolder C) {
		super(C, "SCOTUS");
		this.starters = new HashSet<Character>();
		this.starters.add('U');
		this.starters.add('u');
	}
	
	public SCOTUS(int[] prev, int cid) {
		super(prev, new String[] {"us ", "u.s. "}, "U.S.", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		int entry = this.pages[0];
		int page = this.pages[1];
		return String.format(
				"http://caselaw.lp.findlaw.com/scripts/getcase.pl?navby=case&court=us&vol=%d&page=%d#%d", 
				volume, entry, page);
	}
	
	public SCOTUS newInstance(int[] prev) {
		return new SCOTUS(prev, this.citation_type_id);
	}

}
