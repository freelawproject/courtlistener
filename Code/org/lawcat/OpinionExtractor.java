package org.lawcat;

import java.io.*;

import org.pdfbox.pdmodel.PDDocument;
import org.pdfbox.util.PDFTextStripper;

public class OpinionExtractor {
	public static void run(){
		
	}
	
	//convert all pdf files into txt
	public static void AllPDF2txt(){
			
		//list all sub dirs containing string "cir"
	    FileFilter cirDirFilter = new FileFilter() {
	        public boolean accept(File file) {
	            return file.isDirectory() && file.getName().endsWith("cir");
	        }
	    };
		
		File dir = new File(".");
		
		File[] cirDirs = dir.listFiles(cirDirFilter);

		for (int j = 0; j<cirDirs.length; j++ ){	//for each circuit dir
			
			String cirName = cirDirs[j].getName();
						
			//get all pdf file of this circuit
		    FileFilter pdfFilter = new FileFilter() {
		        public boolean accept(File file) {
		            return file.isFile() && file.getName().endsWith(".pdf");
		        }
		    };			
			
			File[] pdfFiles = cirDirs[j].listFiles(pdfFilter);
			for (int  i = 0; i < pdfFiles.length; i++ ){
				
				String fromFilePath = pdfFiles[i].getAbsolutePath();
				String toFileName = cirName + '_' + pdfFiles[i].getName() + ".txt";
				String toFilePath = "txt/" + toFileName;
				
				PDDocument d;
				try {
					
					d = PDDocument.load(fromFilePath);
					
					System.out.println(fromFilePath);
					String text = new PDFTextStripper().getText(d);
					d.close();

					//write text to toFilePath
					File toFile= new File(toFilePath);
					if ( ! toFile.exists() ){
						toFile.createNewFile();
					}
					boolean append = false; 
					FileWriter fstream = new FileWriter(toFile, append);
					BufferedWriter out = new BufferedWriter(fstream);
					out.write(text);
					out.close();
					
				} catch (IOException e) {
					// TODO Auto-generated catch block
					e.printStackTrace();
					continue;
				}
			}
		}
		

	}
}
