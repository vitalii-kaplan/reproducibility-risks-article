## GediNET Pseudocode ##
Function Score(x : two-class dataset , r: number of iteration )<br>
         acc = 0 <br>
         for i = 1 to r <br>
         [x_train, x_test] = split (x, 0.8) // split the data x with ration of 80%-20%<br>
         model = fit(x_train)<br>
         acc = acc+ test(model,x_test)<br>
         return acc/r //the score <br>

Function SubDataSet(D: dataset ,g_set : set of genes )
       D_sub is all the columns of genes that appear on g_set 
                      and all the rows in D
return D_sub


1) Given a two-class dataset D + 
   Groups: each group is a disease name, grp_disease
       [ Each  grp_disease   is a set of genes that are associated with the disease ]
2) Split dataset D into D_train and D_test
3) Select the top 2000 genes by t-test applied on D_train dataset
4) For each disease_i (or groups_i) i=1,....m, perform 
          s = Score(  SubDataSet(D_train, disease_i )
          scores{i}= { disease_i.name, s }  

5) scores = sort (scores, Descending  order)        

Now is the stage of training the model    
   consider the top 10 diseases (or top 2 or 3 ...] 
    genes_train= take all the genes that associated with those top 10 diseases
   D*_train  = SubDataSet(D_train, genes_train)
           represent D_train with just those genes - call it now D*_train
  D*_test  = SubDataSet(D_test, genes_train)
        represent D_test with just those genes - call now D*_test
   final_model = fit(D*_train)
   acc = test(model,D*_test)
