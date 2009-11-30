package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.util.ResourceHolder;


public class FedRCivP extends Rule {

	public FedRCivP(ResourceHolder C) {
		super(C, "FRCivP");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FedRCivP(int[] prev, int cid) {
		super(prev,
				new String[] {"fed. r. civ. p.", "federal rule of civil procedure", "federal rules of civil procedure"},
				"Fed. R. Civ. P. ",
				cid);
	}
	
	public FedRCivP newInstance(int[] prev) {
		return new FedRCivP(prev, this.citation_type_id);
	}
	
	public String citation_url(int index) {
		String result =  String.format("http://www.law.cornell.edu/rules/frcp/Rule%d.htm",
				Integer.parseInt(this.rules[index]));
		result += "#Rule" + this.rules[index];
		if (this.subsections[index].length > 0) {
			result += "_" + this.subsections[index][0] + "_";
		}
		return result;
	}

}
