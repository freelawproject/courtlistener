package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.extractors.CitationExtractor;
import com.robocourt.util.ResourceHolder;


public class USPatent extends Rule {

	public USPatent(ResourceHolder C) {
		super(C, "USPatent");
		this.starters = new HashSet<Character>();
		this.starters.add('U');
		this.starters.add('u');
		this.starters.add('P');
		this.starters.add('p');
	}
	
	public USPatent(int[] prev, int cid) {
		super(prev,
				new String[] {"u.s. patent", "patent no", "patent number"},
				"U.S. Patent No. ",
				cid);
	}
	
	public USPatent newInstance(int[] prev) {
		return new USPatent(prev, this.citation_type_id);
	}
	
	private static String FormatWithCommas(String str) {
		if (str.length() == 0)
			return str;
		String result = "" + str.charAt(str.length() - 1);
		for (int i = 1; i < str.length(); ++i) {
			if (i % 3 == 0)
				result = "," + result;
			result = str.charAt(str.length() - 1 - i) + result;
		}
		return result;
	}
	
	public String citation_url(int index) {
		String result =  String.format("http://www.google.com/patents?vid=USPAT%d",
				Integer.parseInt(this.rules[index]));
		return result;
	}

	public String citation_string(int index) {
		return this.display_name + FormatWithCommas(this.rules[index]);
	}
	
	public String sort_order(int index) {
		return String.format("%08d", Integer.parseInt(this.rules[index]));
	}
	
	public int info_type() {
		return CitationExtractor.PATENT_TYPE;
	}
}
