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

public class SCOTUS extends Reporter implements CitationType {
	
	public SCOTUS(ResourceHolder C) {
		super(C, "SCOTUS");
		this.starters = new HashSet<Character>();
		this.starters.add('U');
		this.starters.add('u');
	}
	
	public SCOTUS(int[] prev, int cid) {
		super(prev, new String[] {"us ", "u.s. "}, "U.S.", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		int entry = this.pages[0];
		int page = this.pages[1];
		return String.format(
				"http://caselaw.lp.findlaw.com/scripts/getcase.pl?navby=case&court=us&vol=%d&page=%d#%d", 
				volume, entry, page);
	}
	
	public SCOTUS newInstance(int[] prev) {
		return new SCOTUS(prev, this.citation_type_id);
	}

}
