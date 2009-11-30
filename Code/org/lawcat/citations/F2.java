package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class F2 extends Reporter implements CitationType {
	
	public F2(ResourceHolder C) {
		super(C, "Fed2");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public F2(int[] prev, int cid) {
		super(prev, new String[] {"f.2d", "f. 2d"}, "F.2d", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "http://altlaw.org/v1/search?command=search+cases&q=" + this.volume + "+F.2d+" + this.pages[0];
	}
	
	public F2 newInstance(int[] prev) {
		return new F2(prev, this.citation_type_id);
	}

}
