## Usage of the Knime workflow and Environment Settings: ##
The workflow contains python and R scripts in it. Hence, to avoid any error, one needs to set up the KNIME Python settings following this path inside KNIME :
<br>
File -> Preferences -> KNIME(left side of the pop-up) -> Python
<br>
And your R server needs to be (open) running simultaneously when the execution starts. 
To be able to open this please use following commands in your R / RStudio:
- library(Rserve);
- Rserve(args = "--vanilla")
<br>
Additionally, you need to install the library('RobustRankAggreg') that is used to aggregate the ranked lists of groups and genes.
