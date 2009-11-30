package com.robocourt.extractors.citations;

/*
 * Reporter-type citation matcher.
 */

import java.util.HashMap;

import com.robocourt.extractors.CitationExtractor;
import com.robocourt.util.ResourceHolder;

public class Reporter extends SubstringMatcher implements CitationType {
	
	protected int[] pages = new int[3];
	// index 0: entry/citation page
	// index 1: start of specific reference
	// index 2: end of specific reference
	protected int volume;
	protected int[] previous_numbers;
	protected String display_name;
	protected int citation_type_id;
	
	public Reporter(ResourceHolder C, String db_name) {
		this.previous_numbers = new int[0];
		this.matching_strings = new String[0];
		this.citation_type_id = C.getCitationTypeID(db_name);
		init();
	}
	
	public Reporter(int[] prev, String[] matching, String dn,  int cid) {
		this.previous_numbers = new int[prev.length];
		for (int i = 0; i < prev.length; ++i)
			this.previous_numbers[i] = prev[i];
		this.matching_strings = matching;
		this.display_name = dn;
		this.citation_type_id = cid;
		init();
	}
	
	private void init() {
		this.indexes = new int[this.matching_strings.length];
		this.finished = false;
		this.more_info = false;
		this.input = "";
		if (this.previous_numbers.length > 0
				&& this.previous_numbers[0] > 0
				&& this.previous_numbers[0] < 1000) {
			this.volume = this.previous_numbers[0];
		}
		else {
			this.volume = -1;
			for (int i = 0; i < indexes.length; ++i) {
				// mark it as a failure
				indexes[i] = -1;
			}
		}
	}
	
	private void AddInformation(int entry, int start, int end) {
		// If no entry==start==end for one of the two, then it means
		// that we are citing the entire opinion
		if (this.pages[0] > 0 &&
				this.pages[0] == this.pages[1] &&
				this.pages[1] == this.pages[2])
			return;
		if (entry == start && start == end) {
			this.pages[1] = this.pages[0];
			this.pages[2] = this.pages[1];
			return;
		}
		if (entry != -1 && this.pages[0] == 0) {
			this.pages[0] = entry;
			this.finished = true;
		}
		if (start != -1) {
			if (this.pages[1] == 0)
				this.pages[1] = start;
			else
				this.pages[1] = Math.min(this.pages[1], start);
			if (end != -1)
				this.pages[2] = Math.max(this.pages[2], end);
			else
				this.pages[2] = Math.max(start, this.pages[2]);
		}
		else {
			this.pages[1] = Math.max(this.pages[0], this.pages[1]);
			this.pages[2] = Math.max(this.pages[1], this.pages[2]);
		}
	}

	public void AddInformation(HashMap<String, String>[] info) {
		//System.out.println("info received: " + info.length);
		if (info == null || info.length == 0)
			return;
		for (int i = 0; i < info.length; ++i) {
			try {
				int entry = -1;
				int start = -1;
				int end = -1;
				if (info[i].containsKey("entry"))
					entry = Integer.parseInt(info[i].get("entry"));
				if (info[i].containsKey("start"))
					start = Integer.parseInt(info[i].get("start"));
				if (info[i].containsKey("end"))
					end = Integer.parseInt(info[i].get("end"));
				AddInformation(entry, start, end);
			}
			catch (Exception e) {
				System.out.println("Error in receiving data for Reporter:");
				e.printStackTrace();
				continue;
			}
		}
	}
	
	public int num_citations() {
		return 1;
	}

	public String citation_string(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		int entry = this.pages[0];
		int start = this.pages[1];
		int end = this.pages[2];
		String citation = volume + " " + this.display_name + " " + entry;
		if (end > entry) {
			if (end > start)
				citation += ", " + start + "-" + end;
			else
				citation += ", " + start;
		}
		return citation;
	}
	
	public String citation_url(int index) {
		return null;
	}

	public CitationType newInstance(int[] prev) {
		return null;
	}
	
	public int info_type() {
		return CitationExtractor.OPINION_TYPE;
	}
	
	public int Distance(CitationType type, HashMap<String, String>[] info) {
		int distance = CitationType.INFINITY;
		if (type.getClass().equals(this.getClass())) {
			Reporter t = (Reporter)type;
			if (t.volume != this.volume || !info[0].containsKey("start"))
				return CitationType.INFINITY;
			int page = Integer.parseInt(info[0].get("start"));
			if (this.pages.length > 0 &&
					this.pages[0] < page && page - this.pages[0] < distance)
				distance = page - this.pages[0];
		}
		//System.out.println("distance = " + distance);
		return distance;
	}
	
	public int citation_type_id() {
		return this.citation_type_id;
	}
	
	public String sort_order(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return String.format("%03d%06d", this.volume, this.pages[0]);
	}
	
	public boolean merge(CitationType type) {
		if (type.getClass().equals(this.getClass())) {
			Reporter t = (Reporter)type;
			if (t.volume != this.volume || t.pages[0] != this.pages[0])
				return false;
			AddInformation(t.pages[0], t.pages[1], t.pages[2]);
			return true;
		}
		return false;
	}

}
