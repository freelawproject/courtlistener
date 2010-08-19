// This software and any associated files are copyright 2010 Brian Carver, 
// Michael Lissner and Longhao Wang.
// 
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
// 
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
// 
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.


package com.robocourt.extractors.citations;

import java.util.HashSet;

import com.robocourt.util.ResourceHolder;


public class FedRCrimP extends Rule {

	public FedRCrimP(ResourceHolder C) {
		super(C, "FRCrimP");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FedRCrimP(int[] prev, int cid) {
		super(prev,
				new String[] {"fed. r. crim. p.", "federal rule of ciminal procedure", "federal rules of criminal procedure"},
				"Fed. R. Crim. P. ",
				cid);
	}
	
	public FedRCrimP newInstance(int[] prev) {
		return new FedRCrimP(prev, this.citation_type_id);
	}
	
	protected String JoinSubsectionPiecesForURL(int index) {
		String result = "";
		if (this.subsections[index].length > 0) {
			result = "(";
			for (int i = 0 ; i < this.subsections[index].length; ++i) {
				result += this.subsections[index][i];
				if (i < this.subsections[index].length - 1) result += ")(";
			}
			result += ")";
		}
		return result;
	}
	
	public String citation_url(int index) {
		String result =  String.format("http://www.law.cornell.edu/rules/frcrmp/Rule%d.htm",
				Integer.parseInt(this.rules[index]));
		String str = JoinSubsectionPiecesForURL(index);
		if (str.length() > 0)
			result += "#Rule" + this.rules[index] + str;
		return result;
	}

}
