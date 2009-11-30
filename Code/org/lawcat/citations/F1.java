package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class F1 extends Reporter implements CitationType {
	
	public F1(ResourceHolder C) {
		super(C, "Fed1");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public F1(int[] prev, int cid) {
		super(prev, new String[] {"f. "}, "F.", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "http://altlaw.org/v1/search?command=search+cases&q=" + this.volume + "+F.+" + this.pages[0];
	}
	
	public F1 newInstance(int[] prev) {
		return new F1(prev, this.citation_type_id);
	}

}
