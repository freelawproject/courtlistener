package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class F3 extends Reporter implements CitationType {
	
	public F3(ResourceHolder C) {
		super(C, "Fed3");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public F3(int[] prev, int cid) {
		super(prev, new String[] {"f.3d", "f. 3d"}, "F.3d", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "http://altlaw.org/v1/search?command=search+cases&q=" + this.volume + "+F.3d+" + this.pages[0];
	}
	
	public F3 newInstance(int[] prev) {
		return new F3(prev, this.citation_type_id);
	}

}
