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

import com.robocourt.extractors.CitationExtractor;

/*
 * Base class for many citation matchers. Sets the status to MORE_INFO_NEEDED
 * when it has matched one of the given strings, but relies on the child class
 * to tell when it's really finished (usually needs to parse some numbers)
 */

public class SubstringMatcher {

	protected int[] indexes;
	protected String input;
	protected boolean more_info;
	protected boolean finished;
	protected String[] matching_strings;  // not case sensitive
	protected HashSet<Character> starters;  // case sensitive
	
	// Checks for equality unless match_against is a space, in which case it
	// checks that c is some whitespace character
	protected boolean Matches(char c, char match_against) {
		if (match_against == ' ' && Character.isWhitespace(c))
			return true;
		if (c == match_against)
			return true;
		return false;
	}

	public int input(char s) {
		s = Character.toLowerCase(s);
		this.input += s;
		//System.out.println(this.input);
		for (int i = 0; i < indexes.length; ++i) {
			if (indexes[i] == -1)
				continue;
			if (Matches(s,this.matching_strings[i].charAt(indexes[i]))) {
				indexes[i] += 1;
				if (indexes[i] == this.matching_strings[i].length()) {
					// made a match
					this.more_info = true;
					break;
				}
			}
			else {
				indexes[i] = -1;
			}
		}
		return status();
	}
	
	public int status() {
		if (this.finished)
			return CitationExtractor.PARSE_COMPLETE;
		if (this.more_info)
			return CitationExtractor.MORE_INFO_NEEDED;
		for (int i = 0; i < indexes.length; ++i) {
			if (indexes[i] > -1)
				return CitationExtractor.PARSE_IN_PROGRESS;
		}
		return CitationExtractor.PARSE_BROKEN;
	}
	
	public boolean start(char c) {
		return starters.contains(c);
	}
	
}
