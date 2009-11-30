package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.util.ResourceHolder;


public class FedRAppP extends Rule {

	public FedRAppP(ResourceHolder C) {
		super(C, "FRAppP");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FedRAppP(int[] prev, int cid) {
		super(prev,
				new String[] {"fed. r. app. p.", "federal rule of appellate procedure", "federal rules of appellate proecudere"},
				"Fed. R. App. P. ",
				cid);
	}
	
	public FedRAppP newInstance(int[] prev) {
		return new FedRAppP(prev, this.citation_type_id);
	}
	
	protected String JoinSubsectionPiecesForURL(int index) {
		String result = "";
		if (this.subsections[index].length > 0) {
			result = "_";
			for (int i = 0 ; i < this.subsections[index].length; ++i) {
				result += this.subsections[index][i];
				if (i < this.subsections[index].length - 1) result += "_";
			}
			result += "_";
		}
		return result;
	}
	
	public String citation_url(int index) {
		String result =  String.format("http://www.law.cornell.edu/rules/frap/rules.html#Rule%d",
				Integer.parseInt(this.rules[index]));
		result += JoinSubsectionPiecesForURL(index);
		return result;
	}

}
