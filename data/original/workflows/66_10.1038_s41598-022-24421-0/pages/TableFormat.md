## Convert gene expression excel format (.xlsx)  to Knime Table format (.table) ##
You need to download the Knime workflow name **ProcessGEO_data.knwf** that takes as input an excel format. 
The following is an example of the structure of an excel format, you can download the source file **GDS484.xlsx**. 
![alt text](https://github.com/malikyousef/PriPath/blob/main/images/GDS484.JPG?raw=true)
# The following is how the Knime workflow look like ##
The node "Read Excel" should be configure to reach the location of the excel file. The workflow will generate an automatic output file named by replacing the file extension of xlsx with table.
![alt text](https://github.com/malikyousef/PriPath/blob/main/images/PreProcessGEO.JPG?raw=true)
## The output table file will look like, also you can download the file that has the name GDS484.table ##
![alt text](https://github.com/malikyousef/PriPath/blob/main/images/GDS484_table_format_image.JPG?raw=true)
