import glob
import os, numpy as np, pandas, statsmodels.api as sm

def BH_selection_egenes(p_simes, level):

    m = p_simes.shape[0]
    p_sorted = np.sort(p_simes)
    indices = np.arange(m)
    indices_order = np.argsort(p_simes)

    #if np.any(p_sorted - np.true_divide(level * (np.arange(m) + 1.), m) <= np.zeros(m)):

    order_sig = np.max(indices[p_sorted - np.true_divide(level * (np.arange(m) + 1.), m) <= 0])
    E_sel = indices_order[:(order_sig+1)]

    return order_sig+1, E_sel

path='/Users/snigdhapanigrahi/non_randomized_Simes_F/'
allFiles = glob.glob(path + "/*.txt")
list_ = []
shapes = []
for file_ in allFiles:
    dataArray = np.loadtxt(file_)
    shapes.append(dataArray.shape[0])
    list_.append(dataArray)
length = len(list_)

print("length", length)

shapes = np.asarray(shapes)
print("shapes", shapes)
v = np.cumsum(shapes)
print("vector", v)
#print("shape", shapes.shape, shapes)
simes_output_0 = np.vstack(list_)
print("dimensions", simes_output_0.shape)

p_simes = simes_output_0[:,1]
print("number of genes", p_simes.shape[0])
sig = BH_selection_egenes(p_simes, 0.10)

print("no of egenes selected", sig[0])

K_0 = sig[0]
E_sel_0 = np.sort(sig[1])
print("selected indices", E_sel_0, E_sel_0.shape[0])

#####################################################
path='/Users/snigdhapanigrahi/randomized_Bon_Z/'
allFiles = glob.glob(path + "/*.txt")
list_ = []
shapes = []
for file_ in allFiles:
    dataArray = np.loadtxt(file_)
    shapes.append(dataArray.shape[0])
    list_.append(dataArray)
length = len(list_)

print("length", length)

shapes = np.asarray(shapes)
print("shapes", shapes)
v = np.cumsum(shapes)
print("vector", v)
#print("shape", shapes.shape, shapes)
simes_output = np.vstack(list_)
print("dimensions", simes_output.shape)

p_simes = simes_output[:,1]
print("number of genes", p_simes.shape[0])
sig = BH_selection_egenes(p_simes, 0.10)

print("no of egenes selected", sig[0])

K = sig[0]
E_sel = np.sort(sig[1])
print("selected indices", E_sel, E_sel.shape[0])

print("intersection", np.intersect1d(E_sel, E_sel_0).shape)
