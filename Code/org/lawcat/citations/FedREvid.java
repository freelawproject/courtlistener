package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.util.ResourceHolder;


public class FedREvid extends Rule {

	public FedREvid(ResourceHolder C) {
		super(C, "FREvid");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FedREvid(int[] prev, int cid) {
		super(prev,
				new String[] {"fed. r. evid."},
				"Fed. R. Evid. ",
				cid);
	}
	
	public FedREvid newInstance(int[] prev) {
		return new FedREvid(prev, this.citation_type_id);
	}
	
	public String citation_url(int index) {
		String result =  String.format("http://www.law.cornell.edu/rules/fre/rules.htm",
				Integer.parseInt(this.rules[index]));
		result += "#Rule" + this.rules[index];
		if (this.subsections[index].length > 0) {
			result += this.subsections[index][0];
		}
		return result;
	}

}
