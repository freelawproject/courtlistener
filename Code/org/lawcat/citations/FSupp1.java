package com.robocourt.extractors.citations;


import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class FSupp1 extends Reporter implements CitationType {
	
	public FSupp1(ResourceHolder C) {
		super(C, "FSupp1");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FSupp1(int[] prev, int cid) {
		super(prev, new String[] {"f. supp. ", "f.supp. "}, "F. Supp.", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "";
	}
	
	public FSupp1 newInstance(int[] prev) {
		return new FSupp1(prev, this.citation_type_id);
	}

}
