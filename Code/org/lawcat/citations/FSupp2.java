package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class FSupp2 extends Reporter implements CitationType {
	
	public FSupp2(ResourceHolder C) {
		super(C, "FSupp2");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FSupp2(int[] prev, int cid) {
		super(prev, new String[] {"f. supp. 2d", "f. supp.2d", "f.supp.2d", "f.supp. 2d"}, "F. Supp. 2d", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "";
	}
	
	public FSupp2 newInstance(int[] prev) {
		return new FSupp2(prev, this.citation_type_id);
	}

}
