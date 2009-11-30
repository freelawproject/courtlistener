package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.util.ResourceHolder;

public class USCode extends Rule {

	private int title;
	private int[] previous_numbers;
	
	public USCode(ResourceHolder C) {
		super(C, "US Code");
		this.starters = new HashSet<Character>();
		this.starters.add('u');
		this.starters.add('U');
		this.previous_numbers = new int[0];
		USCodeInit();
	}
	
	public USCode(int[] prev, int cid) {
		super(prev,
				new String[] {"u.s.c.", "usc", "u. s. c."},
				"U.S.C. &sect; ",
				cid);
		this.previous_numbers = new int[prev.length];
		for (int i = 0; i < prev.length; ++i)
			this.previous_numbers[i] = prev[i];
		USCodeInit();
	}
	
	private void USCodeInit() {
		if (this.previous_numbers.length > 0
				&& this.previous_numbers[0] > 0
				&& this.previous_numbers[0] < 100) {
			this.title = this.previous_numbers[0];
		}
		else {
			this.title = -1;
			for (int i = 0; i < indexes.length; ++i) {
				// mark it as a failure
				indexes[i] = -1;
			}
		}
	}

	public String citation_string(int index) {
		return this.title + " U.S.C. &sect; " + this.rules[index] + JoinSubsectionPiecesForDisplay(index);
	}
	
	public String citation_url(int index) {
		String url = String.format(
				"http://www.law.cornell.edu/uscode/html/uscode%02d/usc_sec_%02d_%08d----000-.html",
				this.title, this.title, Integer.parseInt(this.rules[index]));
		if (this.subsections[index].length > 0) {
			url += "#" + JoinSubsectionPiecesForURL(index);
		}
		return url;
	}
	
	public USCode newInstance(int[] prev) {
		return new USCode(prev, this.citation_type_id);
	}
	
	public String sort_order(int index) {
		return String.format("%02d%06d", this.title, Integer.parseInt(this.rules[index]));
	}
	
	public boolean merge(CitationType type) {
		if (type.getClass().equals(this.getClass())) {
			USCode t = (USCode)type;
			if (t.title != this.title)  // Threshold title match
				return false;
			// Merge if there is any match in section
			boolean match_found = false;
			for (int i = 0; i < this.rules.length && !match_found; ++i) {
				for (int j = 0; j < t.rules.length && !match_found; ++j) {
					//System.out.println("Comparing " + this.getClass() + ": " + this.rules[i] + " vs. " + t.rules[j]);
					if (this.rules[i].equals(t.rules[j]))
						match_found = true;
				}
			}
			if (match_found) {
				//System.out.println("Merging " + this.getClass());
				for (int j = 0; j < t.rules.length; ++j) {
					this.AddNewSection(t.rules[j], t.subsections[j]);
				}
				return true;
			}
		}
		return false;
	}

}
