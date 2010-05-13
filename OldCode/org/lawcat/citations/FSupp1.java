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

public class FSupp1 extends Reporter implements CitationType {
	
	public FSupp1(ResourceHolder C) {
		super(C, "FSupp1");
		this.starters = new HashSet<Character>();
		this.starters.add('F');
		this.starters.add('f');
	}
	
	public FSupp1(int[] prev, int cid) {
		super(prev, new String[] {"f. supp. ", "f.supp. "}, "F. Supp.", cid);
	}
	
	public String citation_url(int index) {
		if (index > 0)
			throw new IndexOutOfBoundsException();
		return "";
	}
	
	public FSupp1 newInstance(int[] prev) {
		return new FSupp1(prev, this.citation_type_id);
	}

}
