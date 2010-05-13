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


package org.lawcat.citations;

import java.util.HashMap;

/*
 * A CitationType is like a state machine that is fed characters by a CitationExtractor.
 * It just needs to parse the information that it is fed and say when it has successfully
 * parsed a citation or when it has given up.
 * 
 * The design is a little weird: the extractor holds a CitationType object o1, which is
 * actually a factory. Each time you want to actually start sending characters,
 * you need to create a new object o2 by calling newInstance on o1. Then feed o2 characters.
 */

public interface CitationType {
	public static final int INFINITY = Integer.MAX_VALUE;
	
	public CitationType newInstance(int[] prev);
	
	// Add another character
	public int input(char s);
	
	// Can a new parser by started with this character?
	public boolean start(char s);

	// status code
	public int status();
	
	// number of citations held
	public int num_citations();
	
	// Get string giving parsed citation in proper format
	public String citation_string(int index);
	
	// Get url for full citation
	public String citation_url(int index);
	
	// Get sort order for citation
	public String sort_order(int index);
	
	// Add information like section or page numbers
	public void AddInformation(HashMap<String, String>[] info);
	
	// Type of information it needs
	public int info_type();
	
	public int Distance(CitationType t, HashMap<String, String>[] info);
	
	// Get ID for type of citation
	public int citation_type_id();
	
	// Attempt to merge with another citation; return true if it worked
	public boolean merge(CitationType t);
}
