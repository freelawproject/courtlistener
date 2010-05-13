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

public class FSupp2 extends Reporter implements CitationType {
	
	public FSupp2(ResourceHolder C) {
		super(C, "FSupp2");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FSupp2(int[] prev, int cid) {
		super(prev, new String[] {"f. supp. 2d", "f. supp.2d", "f.supp.2d", "f.supp. 2d"}, "F. Supp. 2d", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "";
	}
	
	public FSupp2 newInstance(int[] prev) {
		return new FSupp2(prev, this.citation_type_id);
	}

}
