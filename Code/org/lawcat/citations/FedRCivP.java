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
