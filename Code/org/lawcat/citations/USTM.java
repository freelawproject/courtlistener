package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.extractors.CitationExtractor;
import com.robocourt.util.ResourceHolder;


public class USTM extends Rule {

	public USTM(ResourceHolder C) {
		super(C, "USTM");
		this.starters = new HashSet<Character>();
		this.starters.add('R');
		this.starters.add('r');
	}
	
	public USTM(int[] prev, int cid) {
		super(prev,
				new String[] {"registration no", "registration number"},
				"Registration No. ",
				cid);
	}
	
	public USTM newInstance(int[] prev) {
		return new USTM(prev, this.citation_type_id);
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
		String result =  "http://tarr.uspto.gov/tarr?regser=registration&action=Request+Status&entry="
			+ this.rules[index];
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
