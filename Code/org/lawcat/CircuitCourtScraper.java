package org.lawcat;


import java.io.File;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.lawcat.*;

/**
 * 
 * @author Longhao Wang 
 * 
 * scrape all circuit court website for the latest opinion, save to local disk
 * 
 * notes on regular expression:
 * ? in URL should be written in regex as \\?
 * reference: http://java.sun.com/javase/7/docs/api/java/util/regex/Pattern.html
 */
public class CircuitCourtScraper {
	

	
	public static void run(){
		createCircuitDir();
		
		get1stCir();
		
		get2ndCir();
		
		get3rdCir();
		
		get4thCir();
		
		get5thCir();
		
		get6thCir();
		
		get7thCir();
		
		get8thCir();
		
		get9thCir();
		
		get10thCir();
		
		get11thCir();
		
		getDCCir();
		
		getFedCir();
	}
	

	/**
	 * create one directory for each circuit court
	 * 1 - 11 circuit, DC circuit, Federal circuit
	 */
	public static void createCircuitDir(){
		
		//1 - 11 circuit
		for ( int i = 1; i<= 11; i++ ){
			File dir = new File( Integer.toString(i) +  "cir");
			if (! dir.exists() ){
				dir.mkdir();
			}
		}	
		
		//one dir for dc circuit
		File dir = new File( "DCcir");
		if (! dir.exists() ){
			dir.mkdir();
		}
		
		//one dir for federal circuit
		dir = new File( "FEDcir");
		if (! dir.exists() ){
			dir.mkdir();
		}
	}
	
	public static void get1stCir(){
		
		//construct query URL. 
		//e.g. http://www.ca1.uscourts.gov/cgi-bin/opinions.pl?FROMDATE=10/05/09&TODATE=11/05/09
		Date today = new Date();
		Calendar c = new GregorianCalendar();
		
		// query from today to a month ago
		System.out.println("Processing First Circuit...");
		String end = new SimpleDateFormat("MM/dd/yy").format(today);
		c.setTime(today);
		c.add(Calendar.MONTH, -1);
		String begin = new SimpleDateFormat("MM/dd/yy").format(c.getTime());
		
		//the URL that contains links to opinions
		//e.g. http://www.ca1.uscourts.gov/cgi-bin/opinions.pl?FROMDATE=10/05/09&TODATE=11/05/09
		String getStr = "http://www.ca1.uscourts.gov/cgi-bin/opinions.pl?FROMDATE=" + begin + "&TODATE=" + end;
		
		System.out.println(getStr);
		Log.writeLog(getStr);
		
		//get the webpage content as string
		String pageContent = GetPage.readPage2Str(getStr);
		

		Pattern pat;
		//robocourt: pat = Pattern.compile("(\\d\\d\\d\\d/\\d\\d/\\d\\d)\\s*<td align=center><a href=([^>]+)[^&]+&nbsp;([^<]+)<");
		//match result: "2009/10/07	<td align=center><a href=/cgi-bin/getopn.pl?OPINION=08-2515P.01A>08-2515P.01A</a>	<td align=center><a href=/paceruser.html>        08-2515</a>        <td>&nbsp;Sugarloaf Funding, LLC v. US Dept of the Treasury                <"
		/*
		 * longhao's explanation for robocourt code: 
		 * \\ becuase in "", \\ stand for \
		 * 
		 * ( ) -> group; 
		 * 
		 * \\d\\d\\d\\d/\\d\\d/\\d\\d -> 2009/10/07; 
		 * \\s	A whitespace character
		 *  *    zero or more times
		 * <td align=center><a href=   -> match <td align=center><a href=
		 * 
		 * ([^>]+)[^&]+&nbsp;([^<]+)<" 
		 * 				/cgi-bin/getopn.pl?OPINION=08-2515P.01A>08-2515P.01A</a>	<td align=center><a href=/paceruser.html>        08-2515</a>        <td>&nbsp;Sugarloaf Funding, LLC v. US Dept of the Treasury                <
		 * [^>]   		any character except >
		 * ([^>]+)  	one or more times   -> /cgi-bin/getopn.pl?OPINION=08-2515P.01A>08-2515P.01A</a
		 * [^&]+    	any character except &, one or more  -> >	<td align=center><a href=/paceruser.html>        08-2515</a>        <td>
		 * &nbsp;  		&nbsp;
		 * ([^<]+)  	one or more characters, not including <    -> "Sugarloaf Funding, LLC v. US Dept of the Treasury                "
		 * <   			<
		 * 
		 */

		//longhao: find "/cgi-bin/getopn.pl?OPINION=08-1893P.01A" from "<a href=/cgi-bin/getopn.pl?OPINION=08-1893P.01A>"
		//download URL: http://www.ca1.uscourts.gov/cgi-bin/getopn.pl?OPINION=08-1974P.01A
		pat = Pattern.compile("/cgi-bin/getopn.pl\\?OPINION=([^>]+)");
				
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
						
			//html: http://www.ca1.uscourts.gov/cgi-bin/getopn.pl?OPINION=08-2588P.01A
			//pdf: find in html something like http://www.ca1.uscourts.gov/pdf.opinions/08-2588P-01A.pdf
			
			String opinionURL = "http://www.ca1.uscourts.gov" + m.group();
			//e.g. m.group() = /cgi-bin/getopn.pl?OPINION=08-1402P.01A
			
			//get local file name
			String[] splitURL = opinionURL.split("=");
			String localFileName = splitURL[1] + ".html";
			
			//save html  in 1cir/localFileName
			WebDownloader.Save(opinionURL, "1cir/"+localFileName);
			Log.writeLog(opinionURL + "saved as " + "1cir/"+localFileName);
			
			//find the URL of PDF opinion
			//read the local file as string
			String fileAsStr = ReadFileAsStr.read("1cir/"+localFileName);
			
			//find .pdf, e.g. http://www.ca1.uscourts.gov/pdf.opinions/08-2588P-01A.pdf
			Pattern PDFpat = Pattern.compile("http://www.ca1.uscourts.gov/pdf.opinions/[^.]+.pdf");
			Matcher matcher = PDFpat.matcher(fileAsStr);
			
			if (! matcher.find() ) 
				Log.writeLog("PDF not found, " + localFileName);
				
			String PDFurl = matcher.group();
			
			//local pdf file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			//download pdf 
			WebDownloader.Save(PDFurl, "1cir/"+local_PDF_filename);

		}
		
		
	}
	
	
	public static void get2ndCir(){

		String pageContent = "";
		String pageURL = "http://www.ca2.uscourts.gov/decisions";
		
		Date today = new Date();
		Calendar c = new GregorianCalendar();
		c.setTime(today);
		c.add(Calendar.DATE, -30);
		String m2 = new SimpleDateFormat("MM").format(c.getTime());
		String y2 = new SimpleDateFormat("yyyy").format(c.getTime());
		String d2 = new SimpleDateFormat("dd").format(c.getTime());
		
		//POST parameters, name and value of parameters comes from the FORM of http://www.ca2.uscourts.gov/opinions.htm
		String data = "IW_DATABASE=OPN&IW_FIELD_TEXT=*&IW_FILTER_DATE_AFTER=" + y2 + m2 + d2 + "&IW_BATCHSIZE=20&IW_SORT=-DATE";

		pageContent = POSTgetpage.run(pageURL, data);
	
		//content == the search result page html

		//find url to opinion text
		//e.g. <a href="/decisions/isysquery/dc344fa1-12a5-4815-8a3a-efe03dc17039/1/doc/08-2111-cv_opn.pdf#xml=http://www.ca2.uscourts.gov/decisions/isysquery/dc344fa1-12a5-4815-8a3a-efe03dc17039/1/hilite/">
		
		Pattern pat;
		pat = Pattern.compile("/decisions/isysquery/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
		
			String PDFurl = "http://www.ca2.uscourts.gov" + m.group();
	
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save pdf  in 2cir/localFileName
			WebDownloader.Save(PDFurl, "2cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "2cir/"+local_PDF_filename);
		 
		}
		
		
	}
	
	public static void get3rdCir(){
		//recent precedential
		//http://www.ca3.uscourts.gov/recentop/week/recprec.htm
		get3rdCir_precedential();
		
		//recent non-precedential
		//http://www.ca3.uscourts.gov/recentop/week/recnonprec.htm
		get3rdCir_non_precedential();
	}
	
	public static void get3rdCir_precedential(){
		
		String pageURL = "http://www.ca3.uscourts.gov/recentop/week/recprec.htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. 'http://www.ca3.uscourts.gov/opinarch/074673np.pdf'
		Pattern pat = Pattern.compile("http://www.ca3.uscourts.gov/opinarch/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {

			String PDFurl =  m.group();

			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 3cir/localFileName
			WebDownloader.Save(PDFurl, "3cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "3cir/"+local_PDF_filename);

		}
	}

	public static void get3rdCir_non_precedential(){
		
		String pageURL = "http://www.ca3.uscourts.gov/recentop/week/recnonprec.htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. 'http://www.ca3.uscourts.gov/opinarch/074673np.pdf'
		Pattern pat = Pattern.compile("http://www.ca3.uscourts.gov/opinarch/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {

			String PDFurl =  m.group();

			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "3cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "3cir/"+local_PDF_filename);

		}
	}	
	
	public static void get4thCir(){
		/*
		   "http://pacer.ca4.uscourts.gov/lastweek.htm",
		   "http://pacer.ca4.uscourts.gov/opinions_week.htm",
		   "http://pacer.ca4.uscourts.gov/opinions_today.htm"
		*/
		get4thCir_lastweek();
		get4thCir_week();
		get4thCir_today();
	}
	
	public static void get4thCir_lastweek(){
		
		String pageURL = "http://pacer.ca4.uscourts.gov/lastweek.htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. "opinion.pdf/097510.U.pdf"
		Pattern pat = Pattern.compile("opinion.pdf/[^\"]+[PU].pdf");
			
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {

			String PDFurl =  "http://pacer.ca4.uscourts.gov/" + m.group();
			System.out.println(PDFurl);

			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "4cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "4cir/"+local_PDF_filename);

		}
	}
	
	public static void get4thCir_week(){
		String pageURL = "http://pacer.ca4.uscourts.gov/opinions_week.htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. "opinion.pdf/097510.U.pdf"
		Pattern pat = Pattern.compile("opinion.pdf/[^\"]+[PU].pdf");
			
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {

			String PDFurl =  "http://pacer.ca4.uscourts.gov/" + m.group();
			System.out.println(PDFurl);

			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "4cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "4cir/"+local_PDF_filename);

		}		
	}
	public static void get4thCir_today(){
		String pageURL = "http://pacer.ca4.uscourts.gov/opinions_today.htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. "opinion.pdf/097510.U.pdf"
		Pattern pat = Pattern.compile("opinion.pdf/[^\"]+[PU].pdf");
			
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {

			String PDFurl =  "http://pacer.ca4.uscourts.gov/" + m.group();
			System.out.println(PDFurl);

			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "4cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "4cir/"+local_PDF_filename);

		}			
	}
	
	public static void get5thCir(){
	
		//page url: http://www.ca5.uscourts.gov/Opinions.aspx?View=Last7
		String pageURL = "http://www.ca5.uscourts.gov/Opinions.aspx?View=Last7";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		// find "/fdocs/docs.fwx?submit=showbr&shofile=08-2729_002.pdf"
		Pattern pat = Pattern.compile("opinions\\\\([^\"]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		
		while (m.find()) {

			String extractStr = m.group(); //string extracted from webpage
			
			//opinions\pub\06/06-30262-CV1.wpd.pdf			
			//download url, http://www.ca5.uscourts.gov/opinions/pub/08/08-60792-CV0.wpd.pdf
			
			String correctStr = extractStr.replace('\\', '/'); //correct slash in url
			String PDFurl = "http://www.ca5.uscourts.gov/" + correctStr;
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			//save pdf  in 5cir/localFileName
			WebDownloader.Save(PDFurl, "5cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "5cir/"+local_PDF_filename);
			
		}
	}
	
	public static void get6thCir(){
		
		//contruct GET page url
		Date today = new Date();
		Calendar c = new GregorianCalendar();
		c.setTime(today);
		c.add(Calendar.MONTH, -1);
		String d = new SimpleDateFormat("MM/dd/yyyy").format(c.getTime());
		String pageURL = "http://www.ca6.uscourts.gov/cgi-bin/opinions.pl?FROMDATE=" + d;
		String pageContent = GetPage.readPage2Str(pageURL);
			
		// find "/opinions.pdf/09a0705n-06.pdf"
		Pattern pat = Pattern.compile("/opinions\\.pdf/\\w+-\\w+\\.pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		
		while (m.find()) {
			
			String extractStr = m.group(); //string extracted from webpage
			
			//http://www.ca6.uscourts.gov/opinions.pdf/09a0372p-06.pdf
			String PDFurl = "http://www.ca6.uscourts.gov" +extractStr;
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			//save pdf  in 5cir/localFileName
			WebDownloader.Save(PDFurl, "6cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "6cir/"+local_PDF_filename);
		
		}		
		

		
	}
	
	public static void get7thCir(){
		//http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=Past%20Month&&dtype=Opinion
		String pageURL = "http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=Past%20Month&&dtype=Opinion";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		// find "/fdocs/docs.fwx?submit=showbr&shofile=08-2729_002.pdf"
		Pattern pat = Pattern.compile("/fdocs/docs.fwx\\?submit=showbr&shofile=([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		
		while (m.find()) {

			// m.group() = e.g. /fdocs/docs.fwx?submit=showbr&shofile=08-2729_002.pdf
			String PDFurl = "http://www.ca7.uscourts.gov" + m.group();  //e.g. http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=showbr&shofile=09-8027_001.pdf
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("=");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			//save html  in 7cir/localFileName
			WebDownloader.Save(PDFurl, "7cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "7cir/"+local_PDF_filename);	
		}
	}
	
	public static void get8thCir(){
		String rssURL = "http://www.ca8.uscourts.gov/rss/ca8opns_rss.xml";
		
		//save rss file (contains human excerpt)
		Date today = new Date();
		String dayStr = new SimpleDateFormat("MM_dd_yyyy").format(today);
		String rssFileName = dayStr + "_rss.xml";
		WebDownloader.Save(rssURL, "8cir/"+rssFileName);
		
		//find pdf url
		String rssContent = ReadFileAsStr.read("8cir/"+rssFileName);
		Pattern pat = Pattern.compile("http://www.ca8.uscourts.gov/opndir/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(rssContent);
		while (m.find()) {
			
			// m.group() = e.g. http://www.ca8.uscourts.gov/opndir/09/11/082878U.pdf
			String PDFurl = m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			//save html  in 8cir/localFileName
			WebDownloader.Save(PDFurl, "8cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "1cir/"+local_PDF_filename);			

		}
	}
	
	public static void get9thCir(){
		//recent 250 opinions, around 4 months
		//http://www.ca9.uscourts.gov/opinions/?o_mode=view&amp;o_sort_field=19&amp;o_sort_type=DESC&o_page_size=250
		String pageURL = "http://www.ca9.uscourts.gov/opinions/?o_mode=view&amp;o_sort_field=19&amp;o_sort_type=DESC&o_page_size=250";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//find pdf string, e.g. /datastore/opinions/2009/11/02/08-35561.pdf
		Pattern pat = Pattern.compile("/datastore/opinions/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			
			// m.group() = /datastore/opinions/2009/11/04/07-50546.pdf or /datastore/opinions/2009/11/05/no_opinions.pdf or /datastore/opinions/2009/11/05/0617328ebo.pdf
			
			//pdf url: http://www.ca9.uscourts.gov/datastore/opinions/2009/11/05/05-30303.pdf
			String PDFurl = "http://www.ca9.uscourts.gov" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "9cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "1cir/"+local_PDF_filename);
			
		}
		
	}

	public static void get10thCir(){
		
		//archived opinions
		//http://www.ca10.uscourts.gov/opinions/
		
		//recent opinions
		//http://www.ca10.uscourts.gov/clerk/opinions.php
		
		String pageURL = "http://www.ca10.uscourts.gov/clerk/opinions.php";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		// "/opinions/09/09-1308.pdf
		Pattern pat = Pattern.compile("/opinions/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			
			//pdf url: http://www.ca10.uscourts.gov/opinions/08/08-4087.pdf
			String PDFurl = "http://www.ca10.uscourts.gov" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "10cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "10cir/"+local_PDF_filename);	
		}
	}
	
	public static void get11thCir(){
		//published
		//http://www.ca11.uscourts.gov/opinions/last30daysops.php
		get11thCir_published();
		
		//unpublished
		//http://www.ca11.uscourts.gov/unpub/last30daysops.php
		get11thCir_unpublished();
	}
	
	public static void get11thCir_published(){
		// ops/200911803.pdf
		
		String pageURL = "http://www.ca11.uscourts.gov/opinions/last30daysops.php";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		// "/opinions/09/09-1308.pdf
		Pattern pat = Pattern.compile("ops/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			
			String PDFurl = "http://www.ca11.uscourts.gov/opinions/" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 11cir/localFileName
			WebDownloader.Save(PDFurl, "11cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "11cir/"+local_PDF_filename);	
		}
	}
	
	public static void get11thCir_unpublished(){
		String pageURL = "http://www.ca11.uscourts.gov/unpub/last30daysops.php";

		String pageContent = GetPage.readPage2Str(pageURL);
		
		// "/opinions/09/09-1308.pdf
		Pattern pat = Pattern.compile("ops/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			
			String PDFurl = "http://www.ca11.uscourts.gov/unpub/" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "11cir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "11cir/"+local_PDF_filename);	
		}
	}
	
	public static void getDCCir(){
		//case archive: http://pacer.cadc.uscourts.gov/common/opinions/
		//e.g. http://pacer.cadc.uscourts.gov/common/opinions/
		
		Date today = new Date();
		String m1 = new SimpleDateFormat("MM").format(today);
		String y1 = new SimpleDateFormat("yyyy").format(today);
		
		String pageURL = "http://pacer.cadc.uscourts.gov/common/opinions/" + y1 + m1 + ".htm";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//'/docs/common/opinions/200911/08-5402-1215552.pdf'
		Pattern pat = Pattern.compile("/docs/common/opinions/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			
			String PDFurl = "http://pacer.cadc.uscourts.gov" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "DCcir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "DCcir/"+local_PDF_filename);	
		}		
	}
	
	public static void getFedCir(){
		//http://www.cafc.uscourts.gov/dailylog.html
		String pageURL = "http://www.cafc.uscourts.gov/dailylog.html";
		String pageContent = GetPage.readPage2Str(pageURL);
		
		//   /opinions/09-7018.pdf
		Pattern pat = Pattern.compile("/opinions/([^.]+).pdf");
		
		Matcher m;
		m = pat.matcher(pageContent);
		while (m.find()) {
			// http://www.cafc.uscourts.gov/opinions/08-1352o.pdf
			String PDFurl = "http://www.cafc.uscourts.gov" + m.group();
			
			//local file name
			String[] split_PDF_URL = PDFurl.split("/");
			String local_PDF_filename = split_PDF_URL[split_PDF_URL.length-1];
			
			
			//save html  in 9cir/localFileName
			WebDownloader.Save(PDFurl, "FEDcir/"+local_PDF_filename);
			Log.writeLog(PDFurl + "saved as " + "FEDcir/"+local_PDF_filename);	
		}		
		
	}
}
