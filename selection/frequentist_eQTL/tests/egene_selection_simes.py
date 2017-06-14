from __future__ import print_function
from scipy.stats import norm as normal
import numpy as np
import os

def simes_selection_egene(X,
                          y,
                          randomizer= 'gaussian',
                          noise_level = 1.,
                          randomization_scale=1.):

    n, p = X.shape
    sigma = noise_level

    T_stats = X.T.dot(y) / sigma

    if randomizer == 'gaussian':
        perturb = np.random.standard_normal(p)
        randomized_T_stats = T_stats + randomization_scale * perturb

        p_val_randomized = np.sort(2. * (1. - normal.cdf(np.true_divide(np.abs(randomized_T_stats), np.sqrt(2.)))))

        indices_order = np.argsort(2. * (1. - normal.cdf(np.true_divide(np.abs(randomized_T_stats), np.sqrt(2.)))))

    elif randomizer == 'none':
        perturb = np.zeros(p)
        randomized_T_stats = T_stats + randomization_scale * perturb

        p_val_randomized = np.sort(2. * (1. - normal.cdf(np.true_divide(np.abs(randomized_T_stats), np.sqrt(1.)))))

        indices_order = np.argsort(2. * (1. - normal.cdf(np.true_divide(np.abs(randomized_T_stats), np.sqrt(1.)))))

    simes_p_randomized = np.min((p / (np.arange(p) + 1.)) * p_val_randomized)

    i_0 = np.argmin((p / (np.arange(p) + 1.)) * p_val_randomized)

    t_0 = indices_order[i_0]

    T_stats_active = T_stats[i_0]

    u_1 = ((i_0 + 1.) / p) * np.min(
        np.delete((p / (np.arange(p) + 1.)) * p_val_randomized, i_0))

    if i_0 > p - 2:
        u_2 = -1
    else:
        u_2 = p_val_randomized[i_0 + 1]

    return simes_p_randomized, i_0, t_0, np.sign(T_stats_active), u_1, u_2


if __name__ == "__main__":

    #gene_file = r'/Users/snigdhapanigrahi/Results_freq_EQTL/Muscle_Skeletal_mixture4amp0.30/Muscle_Skeletal_chunk001_mtx/Genes.txt'
    gene_file = r'/scratch/PI/jtaylo/snigdha_data/gtex/simulation_muscle/Muscle_Skeletal_chunk001_mtx/Genes.txt'

    with open(gene_file) as g:
        content = g.readlines()

    content = [x.strip() for x in content]
    ngenes = len(content)
    output = np.zeros((ngenes, 8))

    #path = '/Users/snigdhapanigrahi/Results_freq_EQTL/Muscle_Skeletal_mixture4amp0.30/Muscle_Skeletal_chunk001_mtx/'
    path = '/scratch/PI/jtaylo/snigdha_data/gtex/simulation_muscle/Muscle_Skeletal_chunk001_mtx/'
    outfile = os.path.join(path, "simes_output_test" + str(0) + ".txt")

    for j in range(ngenes):
        X = np.load(os.path.join(path + "X_" + str(content[j]))+".npy")
        n, p = X.shape

        X -= X.mean(0)[None, :]
        X /= (X.std(0)[None, :] * np.sqrt(n))

        y = np.load(os.path.join(path + "y_" + str(content[j]))+".npy")
        y = y.reshape((y.shape[0],))

        beta = np.load(os.path.join(path + "b_" + str(content[j]))+".npy")

        simes = simes_selection_egene(X, y, randomizer='gaussian')

        output[j, 0] = p

        output[j, 1] = np.sum(beta>0.01)

        output[j, 2:] = simes

    np.savetxt(outfile, output)

    #print(np.loadtxt(outfile))


