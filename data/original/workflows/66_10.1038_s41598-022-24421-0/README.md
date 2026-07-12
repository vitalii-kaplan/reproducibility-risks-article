## **GediNET- Discovering Multi-Disease Gene Associations using Established Biological Information and Knowledge-based Machine Learning** <br>
Emma Qumsiyeh<sup>1*</sup>, Louise Showe<sup>2</sup>, and Malik Yousef<sup>3,4*</sup><br>
<sup>1</sup>Information Technology Engineering, Al-Quds University, Palestine<br>
<sup>2</sup>The Wistar Institute, Philadelphia, PA,19104, USA<br>
<sup>3</sup>Department of Information Systems, Zefat Academic College, Zefat, 13206, Israel<br>
<sup>4</sup>Galilee Digital Health Research Center (GDH), Zefat Academic College, Israel<br>
<sup>*</sup>Corresponding authors:<br>
Malik Yousef: malik.yousef@gmail.com<br>
Emma Qumsiyeh: emma.qumsiyeh@hotmail.com<br>


*	Correspondence: malik.yousef@gmail.com;

## To read the paper [click](https://www.researchsquare.com/article/rs-1643219/v1.pdf)<br>
## Knime Workflow
GediNET tool is a Knime workflow. In order to run the workflow, you need to download Knime and install it in your local machine.
This is the link for downloading Knime: https://www.knime.com/downloads<br>
For more information about the Knime platform you might visit https://www.knime.com/software-overview <br>
See this [page](pages/SettingsKnime.md) for information about setting Knime.
<br>
Visit this [page](https://github.com/malikyousef/GediNET/blob/main/pages/TableFormat.md) for instruction in how to prepare the dataset into Knime table format (*.table) using a Knime workflow
<br>
Visit this [page](https://github.com/malikyousef/GediNET/blob/main/pages/GroupingFile.md) for instruction in how to upload the Groups file.  
Visit this [page](https://github.com/malikyousef/GediNET/blob/main/pages/outputs.md) for the outputs of GediNET.
<br> 
The Knime workflow name is "GediNET_v1.knwf" that you might [download](GediNET_v1.knwf) and run throug the [Knime](https://www.knime.com/)platform


**Running the workflow:**

- You need to use the node “MCCV Iterations” in order to specify the number of Monte Carlo Cross Validation (MCCV) iterations, for example 10 or 100.
- You need to configure the node “List Files/Folders” to point it to the folder that has the gene expression dataset in a table format (as described above)
- You might [download](GDS4824.table) an example of such data named [DSD84.table](GDS4824.table)<br>

## The  Pseudocode of GediNET can seen over this [file](pages/Pseudocode.txt) 
## GediNET main workflow is: ##

![alt text](https://github.com/malikyousef/GediNET/blob/main/images/GediNET_main.JPG?raw=true)


 
 ## The content of the MetaNode GediNET is : ##
 
![alt text](https://github.com/malikyousef/GediNET/blob/main/images/GediNET_MetaNode.JPG?raw=true)

 ## The content of the G-S-M component ##
 
 ![alt text](https://github.com/malikyousef/GediNET/blob/main/images/Ttest_and_GSM.JPG?raw=true)

## The 3 main component of G-S-M ##
 ![alt text](https://github.com/malikyousef/GediNET/blob/main/images/G-S-M_all_steps.JPG?raw=true)
