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

import com.robocourt.util.ResourceHolder;

// For now, treats it as a citation into plain US Code
public class USCodeAnnotated extends USCode {
	
	public USCodeAnnotated(int[] prev, int cid) {
		super(prev, cid);
		this.matching_strings =
			new String[] {"u.s.c.s.", "u.s.c.a.",
				"usca", "uscs",
				"u. s. c. a.", "u. s. c. s."};
	}
	
	public USCodeAnnotated(ResourceHolder C) {
		super(C);
	}
	
	public USCode newInstance(int[] prev) {
		return new USCodeAnnotated(prev, this.citation_type_id);
	}

}
